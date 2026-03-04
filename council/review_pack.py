"""ReviewPack assembly — builds the structured context consumed by all reviewers.

Extracts changed symbols, maps test coverage, and packages everything
into a single Pydantic object.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from .config import CouncilConfig
from .schemas import (
    ChangedSymbol,
    DiffContext,
    GateZeroFinding,
    ReviewPack,
)


def _extract_python_symbols(source: str, file_path: str) -> list[ChangedSymbol]:
    """Extract function and class definitions from Python source."""
    symbols: list[ChangedSymbol] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return symbols

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            symbols.append(ChangedSymbol(
                name=node.name,
                kind="class",
                file=file_path,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                change_type="added",  # refined by _filter_to_changed_symbols
                signature=f"class {node.name}",
            ))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Determine if this is a method (inside a class) or a function
            kind = "function"
            # Check parent context — ast.walk doesn't give parents,
            # so we check if the function is nested inside a ClassDef
            for potential_parent in ast.walk(tree):
                if isinstance(potential_parent, ast.ClassDef):
                    if node in ast.iter_child_nodes(potential_parent):
                        kind = "method"
                        break

            # Build signature using ast.unparse for robust annotation rendering
            args = []
            for arg in node.args.args:
                if arg.arg in ("self", "cls"):
                    continue
                ann = ""
                if arg.annotation:
                    try:
                        ann = f": {ast.unparse(arg.annotation)}"
                    except Exception:
                        pass
                args.append(f"{arg.arg}{ann}")

            ret = ""
            if node.returns:
                try:
                    ret = f" -> {ast.unparse(node.returns)}"
                except Exception:
                    pass

            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            sig = f"{prefix} {node.name}({', '.join(args)}){ret}"

            symbols.append(ChangedSymbol(
                name=node.name,
                kind=kind,
                file=file_path,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                change_type="added",  # refined by _filter_to_changed_symbols
                signature=sig,
            ))

    return symbols


def _extract_deleted_symbols(diff_file) -> list[ChangedSymbol]:
    """Extract symbols that were removed from diff hunk removed lines.

    Scans lines starting with '-' in hunks for function/class definitions.
    This is a heuristic approach — it catches simple 'def name(' and 'class name'
    patterns but won't detect multiline signatures. Good enough for catching
    deleted auth checks, removed validation, and breaking API removals.
    """
    import re
    symbols: list[ChangedSymbol] = []
    seen: set[str] = set()

    # Patterns for Python, JS/TS function/class definitions on removed lines
    patterns = [
        # Python: def func_name( or async def func_name(
        re.compile(r"^-\s*(?:async\s+)?def\s+(\w+)\s*\("),
        # Python: class ClassName
        re.compile(r"^-\s*class\s+(\w+)[\s:(]"),
        # JS/TS: function funcName( or export function
        re.compile(r"^-\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\("),
        # JS/TS: export class ClassName
        re.compile(r"^-\s*(?:export\s+)?class\s+(\w+)[\s{]"),
    ]

    for hunk in diff_file.hunks:
        # Track approximate source line number for removed lines
        src_line = hunk.source_start
        for line in hunk.content.splitlines():
            if line.startswith("-"):
                for pattern in patterns:
                    m = pattern.match(line)
                    if m and m.group(1) not in seen:
                        name = m.group(1)
                        seen.add(name)
                        is_class = "class" in line.split(name)[0]
                        symbols.append(ChangedSymbol(
                            name=name,
                            kind="class" if is_class else "function",
                            file=diff_file.path,
                            line_start=src_line,
                            line_end=src_line,
                            change_type="deleted",
                            signature=line.lstrip("-").strip(),
                        ))
                        break
                src_line += 1
            elif not line.startswith("+"):
                src_line += 1  # context line

    return symbols


def _filter_to_changed_symbols(
    all_symbols: list[ChangedSymbol],
    diff_file,
    is_new_file: bool,
) -> list[ChangedSymbol]:
    """Filter symbols to only those overlapping changed line ranges.

    For new files, all symbols are included as 'added'.
    For modified files, only symbols whose definition overlaps a changed hunk
    are included, marked as 'modified'.
    """
    if is_new_file:
        # All symbols in a new file are "added"
        return all_symbols

    # Build changed line ranges from hunks
    changed_ranges: list[tuple[int, int]] = []
    for hunk in diff_file.hunks:
        start = hunk.target_start
        end = hunk.target_start + max(hunk.target_length - 1, 0)
        changed_ranges.append((start, end))

    if not changed_ranges:
        return []

    # Filter to symbols that overlap with at least one changed range
    changed: list[ChangedSymbol] = []
    for sym in all_symbols:
        for range_start, range_end in changed_ranges:
            # Symbol overlaps if its line range intersects the changed range
            if sym.line_start <= range_end and sym.line_end >= range_start:
                sym.change_type = "modified"
                changed.append(sym)
                break

    return changed


def _build_test_coverage_map(diff_context: DiffContext) -> dict[str, list[str]]:
    """Map source files to test files using imports and naming conventions."""

    def _is_test_file(path: str) -> bool:
        low = path.lower()
        name = Path(path).name.lower()
        return (
            path.startswith("tests/")
            or name.startswith("test_")
            or name.endswith("_test.py")
            or name == "conftest.py"
            or "test" in low
        )

    test_entries = [f for f in diff_context.files if _is_test_file(f.path)]
    source_entries = [f for f in diff_context.files if not _is_test_file(f.path)]

    coverage_map: dict[str, list[str]] = {f.path: [] for f in source_entries}

    # Module path map for changed Python source files (e.g. council/cli.py -> council.cli)
    source_modules: dict[str, str] = {}
    for src in source_entries:
        if src.path.endswith('.py'):
            source_modules[src.path] = src.path[:-3].replace('/', '.')

    for test in test_entries:
        if not test.path.endswith('.py'):
            continue

        imports: set[str] = set()
        tree = None
        if test.source_content:
            try:
                tree = ast.parse(test.source_content)
            except SyntaxError:
                tree = None

        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module)
                    for alias in node.names:
                        if alias.name != '*':
                            imports.add(f"{node.module}.{alias.name}")

        matched_by_import = False
        if imports:
            for src_path, module in source_modules.items():
                if any(imp == module or imp.startswith(f"{module}.") for imp in imports):
                    coverage_map[src_path].append(test.path)
                    matched_by_import = True

        # Fallback to filename-stem convention when imports are absent or do not match.
        if not matched_by_import:
            test_stem = Path(test.path).stem
            for src in source_entries:
                if Path(src.path).stem in test_stem:
                    coverage_map[src.path].append(test.path)

    return coverage_map


def _estimate_tokens(text: str) -> int:
    """Rough token estimate."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


def assemble(
    diff_context: DiffContext,
    gate_zero_findings: list[GateZeroFinding],
    config: CouncilConfig,
    skipped_files: list[str] | None = None,
    truncated_files: list[str] | None = None,
) -> ReviewPack:
    """Assemble a ReviewPack from the preprocessed diff context."""
    # Extract symbols from all non-deleted files with source content
    all_symbols: list[ChangedSymbol] = []
    languages: set[str] = set()

    for diff_file in diff_context.files:
        if diff_file.language:
            languages.add(diff_file.language)

        # Extract deleted symbols from removed lines in hunks
        # (works for any language — regex-based, doesn't need source_content)
        if diff_file.change_type in ("deleted", "modified") and diff_file.hunks:
            deleted_syms = _extract_deleted_symbols(diff_file)
            all_symbols.extend(deleted_syms)

        if diff_file.change_type == "deleted" or not diff_file.source_content:
            continue

        if diff_file.language == "python":
            file_symbols = _extract_python_symbols(diff_file.source_content, diff_file.path)
            # Filter to only symbols that overlap with changed line ranges
            changed = _filter_to_changed_symbols(
                file_symbols,
                diff_file,
                is_new_file=(diff_file.change_type == "added"),
            )
            all_symbols.extend(changed)
        # Future: add TypeScript, JavaScript extractors here

    # Build test coverage map
    test_map = _build_test_coverage_map(diff_context)

    # Mark symbols that have tests
    def _is_test_path(path: str) -> bool:
        lower = path.lower()
        name = Path(path).name.lower()
        return (
            path.startswith("tests/")
            or name.startswith("test_")
            or name.endswith("_test.py")
            or name == "conftest.py"
        )

    for symbol in all_symbols:
        tests = test_map.get(symbol.file, [])
        if tests:
            symbol.has_tests = True
            symbol.test_file = tests[0]
        elif _is_test_path(symbol.file):
            symbol.has_tests = True
            symbol.test_file = symbol.file

    # Build the diff text for reviewers with explicit file boundaries
    diff_sections = []
    for f in diff_context.files:
        file_header = f"=== FILE: {f.path} ({f.change_type}) ==="
        hunks_text = "\n".join(h.content for h in f.hunks)
        diff_sections.append(f"{file_header}\n{hunks_text}")
    diff_text = "\n\n".join(diff_sections)

    # Build repo_policies from config settings that affect review behavior
    repo_policies: dict[str, Any] = {
        "require_docs": config.gate_zero.require_docs,
        "require_type_annotations": config.gate_zero.require_type_annotations,
        "require_readme_on_new_module": config.gate_zero.require_readme_on_new_module,
        "check_secrets": config.gate_zero.check_secrets,
        "max_file_lines": config.gate_zero.max_file_lines,
        "enabled_analyzers": {
            lang: enabled
            for lang, enabled in config.gate_zero.analyzers.items()
            if enabled
        },
    }
    if hasattr(config.gate_zero, "documentation"):
        repo_policies["documentation"] = config.gate_zero.documentation

    return ReviewPack(
        diff_text=diff_text,
        changed_files=diff_context.changed_files,
        added_files=diff_context.added_files,
        deleted_files=diff_context.deleted_files,
        changed_symbols=all_symbols,
        test_coverage_map=test_map,
        languages_detected=sorted(languages - {"markdown", "toml", "yaml", "json"}),
        gate_zero_results=gate_zero_findings,
        repo_policies=repo_policies,
        branch=diff_context.branch,
        commit_range=diff_context.commit_range,
        total_lines_changed=diff_context.total_additions + diff_context.total_deletions,
        token_estimate=_estimate_tokens(diff_text),
        files_truncated=truncated_files or [],
        files_skipped=skipped_files or [],
    )

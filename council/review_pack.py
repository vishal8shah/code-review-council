"""ReviewPack assembly — builds the structured context consumed by all reviewers.

Extracts changed symbols, maps test coverage, and packages everything
into a single Pydantic object.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .analyzers.base import is_test_file
from .analyzers.ecmascript import (
    collect_javascript_exports,
    collect_typescript_exports,
)
from .config import CouncilConfig
from .schemas import (
    ChangedSymbol,
    DiffContext,
    GateZeroFinding,
    ReviewPack,
)

_ECMASCRIPT_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")
_ECMASCRIPT_IMPORT_PATTERNS = (
    re.compile(r"""\b(?:import|export)\b[^'"\n]*?\bfrom\s*["'](?P<path>\.[^"']+)["']"""),
    re.compile(r"""\bimport\s*["'](?P<path>\.[^"']+)["']"""),
    re.compile(r"""\bimport\(\s*["'](?P<path>\.[^"']+)["']\s*\)"""),
    re.compile(r"""\brequire\(\s*["'](?P<path>\.[^"']+)["']\s*\)"""),
)


def _normalize_repo_path(path: str) -> str:
    """Normalize repo-relative paths across slash styles without touching disk."""
    parts: list[str] = []
    for part in path.replace("\\", "/").split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _join_repo_path(base_dir: PurePosixPath, relative_path: str) -> str:
    """Resolve a relative repo path against a repo-relative parent directory."""
    base = "/".join(part for part in base_dir.parts if part and part != ".")
    if base:
        return _normalize_repo_path(f"{base}/{relative_path}")
    return _normalize_repo_path(relative_path)


def _normalized_stem(path: str) -> str:
    """Return a lowercase filename stem for repo-relative matching."""
    return Path(_normalize_repo_path(path)).stem.lower()


def _candidate_test_stems(path: str) -> set[str]:
    """Return normalized test stems after stripping common test affixes."""
    stem = _normalized_stem(path)
    candidates = {stem}

    if stem.startswith("test_"):
        candidates.add(stem[5:])
    if stem.endswith("_test"):
        candidates.add(stem[:-5])

    for suffix in (".test", ".spec"):
        if stem.endswith(suffix):
            candidates.add(stem[:-len(suffix)])

    return {candidate for candidate in candidates if candidate}


def _extract_ecmascript_symbols(
    source: str,
    file_path: str,
    language: str,
) -> list[ChangedSymbol]:
    """Extract exported TypeScript/JavaScript symbols from raw source text."""
    collector = (
        collect_typescript_exports
        if language == "typescript"
        else collect_javascript_exports
    )
    lines = source.splitlines()
    symbols: list[ChangedSymbol] = []

    for symbol in collector(source):
        signature = symbol.name
        if 0 < symbol.line_no <= len(lines):
            signature = lines[symbol.line_no - 1].strip()

        symbols.append(ChangedSymbol(
            name=symbol.name,
            kind=symbol.kind,
            file=file_path,
            line_start=symbol.line_no,
            line_end=symbol.line_no,
            change_type="added",  # refined by _filter_to_changed_symbols
            signature=signature,
        ))

    return symbols


def _extract_symbols_for_review_pack(diff_file) -> list[ChangedSymbol]:
    """Dispatch symbol extraction by file language for ReviewPack assembly."""
    if not diff_file.source_content:
        return []

    if diff_file.language == "python":
        return _extract_python_symbols(diff_file.source_content, diff_file.path)
    if diff_file.language in {"typescript", "javascript"}:
        return _extract_ecmascript_symbols(
            diff_file.source_content,
            diff_file.path,
            diff_file.language,
        )
    return []


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
    test_entries = [f for f in diff_context.files if is_test_file(f.path)]
    source_entries = [f for f in diff_context.files if not is_test_file(f.path)]

    coverage_map: dict[str, list[str]] = {f.path: [] for f in source_entries}

    # Module path map for changed Python source files (e.g. council/cli.py -> council.cli)
    source_modules: dict[str, str] = {}
    ecmascript_sources: dict[str, str] = {}
    for src in source_entries:
        normalized = _normalize_repo_path(src.path)
        suffix = Path(normalized).suffix.lower()
        if suffix == ".py":
            source_modules[src.path] = normalized[:-3].replace("/", ".")
        elif suffix in _ECMASCRIPT_EXTENSIONS:
            ecmascript_sources[normalized] = src.path

    def _append_match(source_path: str, test_path: str) -> None:
        if test_path not in coverage_map[source_path]:
            coverage_map[source_path].append(test_path)

    def _python_import_matches(test_source: str | None) -> list[str]:
        if not test_source:
            return []

        imports: set[str] = set()
        tree = None
        try:
            tree = ast.parse(test_source)
        except Exception:
            tree = None

        if tree is None:
            return []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
                for alias in node.names:
                    if alias.name != '*':
                        imports.add(f"{node.module}.{alias.name}")

        matches: list[str] = []
        for src_path, module in source_modules.items():
            if any(imp == module or imp.startswith(f"{module}.") for imp in imports):
                matches.append(src_path)
        return matches

    def _ecmascript_import_matches(test_path: str, test_source: str | None) -> list[str]:
        if not test_source:
            return []

        imports: set[str] = set()
        for pattern in _ECMASCRIPT_IMPORT_PATTERNS:
            for match in pattern.finditer(test_source):
                imports.add(match.group("path"))

        if not imports:
            return []

        test_parent = PurePosixPath(_normalize_repo_path(test_path)).parent
        matched_paths: list[str] = []

        for import_path in imports:
            resolved = _join_repo_path(test_parent, import_path)
            suffix = Path(resolved).suffix.lower()
            candidates: list[str]
            if suffix in _ECMASCRIPT_EXTENSIONS:
                candidates = [resolved]
            else:
                candidates = []
                for ext in _ECMASCRIPT_EXTENSIONS:
                    candidates.append(f"{resolved}{ext}")
                    candidates.append(f"{resolved}/index{ext}")

            for candidate in candidates:
                source_path = ecmascript_sources.get(candidate)
                if source_path and source_path not in matched_paths:
                    matched_paths.append(source_path)

        return matched_paths

    def _fallback_matches(test_path: str) -> list[str]:
        test_stems = _candidate_test_stems(test_path)
        matches: list[str] = []
        for src in source_entries:
            if _normalized_stem(src.path) in test_stems:
                matches.append(src.path)
        return matches

    for test in test_entries:
        normalized_test_path = _normalize_repo_path(test.path)
        suffix = Path(normalized_test_path).suffix.lower()

        matched_paths: list[str] = []
        if suffix == ".py":
            matched_paths = _python_import_matches(test.source_content)
        elif suffix in _ECMASCRIPT_EXTENSIONS:
            matched_paths = _ecmascript_import_matches(test.path, test.source_content)

        # Fallback to filename-stem convention when imports are absent or do not match.
        if not matched_paths:
            matched_paths = _fallback_matches(test.path)

        for source_path in matched_paths:
            _append_match(source_path, test.path)

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

        file_symbols = _extract_symbols_for_review_pack(diff_file)
        if file_symbols:
            changed = _filter_to_changed_symbols(
                file_symbols,
                diff_file,
                is_new_file=(diff_file.change_type == "added"),
            )
            all_symbols.extend(changed)

    # Build test coverage map
    test_map = _build_test_coverage_map(diff_context)

    # Mark symbols that have tests
    for symbol in all_symbols:
        tests = test_map.get(symbol.file, [])
        if tests:
            symbol.has_tests = True
            symbol.test_file = tests[0]
        elif is_test_file(symbol.file):
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

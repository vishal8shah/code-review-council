"""Gate Zero — deterministic static checks, zero LLM cost.

Catches the most common vibe-coding issues before any API call:
  - Missing docstrings / type hints (via language analyzers)
  - Secrets in diff content
  - README not updated for new modules
  - File size sanity
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from .analyzers.registry import get_analyzer
from .config import CouncilConfig, GateZeroConfig
from .schemas import DiffContext, GateZeroFinding, GateZeroResult

# Regex patterns for common secrets
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("AWS Secret Key", re.compile(r"""(?:aws_secret|secret_key|SECRET_KEY)\s*[=:]\s*['"][A-Za-z0-9/+=]{40}['"]""")),
    ("Generic API Key", re.compile(r"""(?:api_key|apikey|API_KEY)\s*[=:]\s*['"][A-Za-z0-9_\-]{20,}['"]""")),
    ("Private Key", re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----")),
    ("GitHub Token", re.compile(r"gh[ps]_[A-Za-z0-9_]{36,}")),
    ("Generic Secret", re.compile(r"""(?:password|passwd|secret)\s*[=:]\s*['"][^'"]{8,}['"]""", re.IGNORECASE)),
]

PROMPT_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(the\s+)?(above|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(chatgpt|gpt|system)", re.IGNORECASE),
    re.compile(r"reveal\s+(the\s+)?system\s+prompt", re.IGNORECASE),
    re.compile(r"developer\s+message", re.IGNORECASE),
]


def _is_test_path(path: str) -> bool:
    p = Path(path)
    posix = p.as_posix()
    name = p.name
    return (
        posix.startswith("tests/")
        or "/tests/" in f"/{posix}"
        or name == "conftest.py"
        or name.startswith("test_")
        or name.endswith("_test.py")
    )



def check_prompt_injection(diff_context: DiffContext) -> list[GateZeroFinding]:
    """Detect prompt-injection strings in ADDED lines."""
    findings: list[GateZeroFinding] = []
    for diff_file in diff_context.files:
        if diff_file.change_type == "deleted":
            continue
        if _is_test_path(diff_file.path):
            continue
        for hunk in diff_file.hunks:
            target_line = hunk.target_start
            for line in hunk.content.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    added = line[1:]
                    if any(p.search(added) for p in PROMPT_INJECTION_PATTERNS):
                        findings.append(GateZeroFinding(
                            check="prompt_injection",
                            severity="HIGH",
                            category="security",
                            file=diff_file.path,
                            line_start=target_line,
                            message="Potential prompt-injection content found in added line",
                            suggestion="Remove instruction-like text from untrusted content or sanitize before LLM use",
                        ))
                    target_line += 1
                elif line.startswith("-") and not line.startswith("---"):
                    pass
                elif line.startswith("@@"):
                    pass
                else:
                    target_line += 1
    return findings


def check_secrets(diff_context: DiffContext) -> list[GateZeroFinding]:
    """Scan diff content for leaked secrets."""
    findings: list[GateZeroFinding] = []
    for diff_file in diff_context.files:
        if diff_file.change_type == "deleted":
            continue
        if _is_test_path(diff_file.path):
            continue
        for hunk in diff_file.hunks:
            # Track actual target line number through the hunk
            target_line = hunk.target_start
            for line in hunk.content.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    # This is an added line — check for secrets
                    for name, pattern in SECRET_PATTERNS:
                        if pattern.search(line):
                            findings.append(GateZeroFinding(
                                check="secret", severity="CRITICAL", category="security",
                                file=diff_file.path,
                                line_start=target_line,
                                message=f"Possible {name} detected in diff",
                                suggestion="Remove the secret and use environment variables instead",
                            ))
                    target_line += 1
                elif line.startswith("-") and not line.startswith("---"):
                    # Removed line — doesn't increment target line counter
                    pass
                elif line.startswith("@@"):
                    # Hunk header — skip (shouldn't appear mid-hunk but be safe)
                    pass
                else:
                    # Context line — exists in both source and target
                    target_line += 1
    return findings


def check_readme_updated(diff_context: DiffContext, config: GateZeroConfig) -> list[GateZeroFinding]:
    """If new public modules are added, README must be in the diff."""
    if not config.require_readme_on_new_module:
        return []

    code_extensions = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"}
    new_public_modules = [
        f for f in diff_context.added_files
        if not Path(f).name.startswith("_")
        and Path(f).suffix in code_extensions
        and "test" not in f.lower()
    ]

    if not new_public_modules:
        return []

    readme_modified = any("readme" in f.lower() for f in diff_context.changed_files)
    if readme_modified:
        return []

    return [GateZeroFinding(
        check="readme", severity="HIGH", category="documentation",
        file="README.md",
        message=f"New public modules added ({', '.join(new_public_modules[:3])}) but README.md not updated",
        suggestion="Update README.md to document new modules/APIs",
    )]


def check_file_size(diff_context: DiffContext, config: GateZeroConfig) -> list[GateZeroFinding]:
    """Flag files that are too large (likely un-decomposed AI dumps)."""
    findings: list[GateZeroFinding] = []
    for diff_file in diff_context.files:
        if diff_file.change_type == "deleted":
            continue
        if _is_test_path(diff_file.path):
            continue
        if diff_file.additions > config.max_file_lines:
            findings.append(GateZeroFinding(
                check="file_size", severity="HIGH", category="architecture",
                file=diff_file.path,
                message=f"File has {diff_file.additions} added lines (threshold: {config.max_file_lines})",
                suggestion="Consider decomposing into smaller, focused modules",
            ))
    return findings


def _changed_line_ranges(diff_file) -> list[tuple[int, int]]:
    """Get the line ranges that were actually modified in the diff."""
    ranges = []
    for hunk in diff_file.hunks:
        start = hunk.target_start
        end = hunk.target_start + hunk.target_length
        ranges.append((start, end))
    return ranges


def _in_changed_range(line: int | None, ranges: list[tuple[int, int]]) -> bool:
    """Check if a line number falls within any changed range."""
    if line is None:
        return True  # if no line info, don't filter it out
    return any(start <= line <= end for start, end in ranges)


def check_language_specific(diff_context: DiffContext, config: GateZeroConfig) -> list[GateZeroFinding]:
    """Run language-specific analyzers (docstrings, type hints) on changed files.

    Only flags functions/classes whose definition overlaps with changed lines
    in the diff — does NOT flag untouched legacy code.
    """
    findings: list[GateZeroFinding] = []

    for diff_file in diff_context.files:
        if diff_file.change_type == "deleted":
            continue
        if _is_test_path(diff_file.path):
            continue
        if diff_file.source_content is None:
            continue

        # Check if this language's analyzer is enabled
        lang = diff_file.language
        if lang and not config.analyzers.get(lang, False):
            continue

        analyzer = get_analyzer(diff_file.path)
        if analyzer is None:
            continue

        # Get changed line ranges for this file
        changed_ranges = _changed_line_ranges(diff_file)

        # For newly added files, check everything
        if diff_file.change_type == "added":
            if config.require_docs:
                findings.extend(analyzer.check_docs(diff_file.source_content, diff_file.path))
            if config.require_type_annotations:
                findings.extend(analyzer.check_types(diff_file.source_content, diff_file.path))
        else:
            # For modified files, only flag items within changed line ranges
            if config.require_docs:
                all_doc_findings = analyzer.check_docs(diff_file.source_content, diff_file.path)
                findings.extend(
                    f for f in all_doc_findings
                    if _in_changed_range(f.line_start, changed_ranges)
                )
            if config.require_type_annotations:
                all_type_findings = analyzer.check_types(diff_file.source_content, diff_file.path)
                findings.extend(
                    f for f in all_type_findings
                    if _in_changed_range(f.line_start, changed_ranges)
                )

    return findings


def check_linters(
    diff_context: DiffContext,
    config: GateZeroConfig,
    repo_root: Path | None = None,
) -> list[GateZeroFinding]:
    """Run configured linters on changed files.

    Only runs linters that have a non-empty command configured.
    Maps each changed file's language to its linter command.
    """
    import shlex
    import subprocess as _sp

    findings: list[GateZeroFinding] = []
    cwd = repo_root or Path.cwd()

    # Build language → linter command mapping (skip empty commands)
    linter_cmds: dict[str, str] = {}
    if config.linters.python:
        linter_cmds["python"] = config.linters.python
    if config.linters.typescript:
        linter_cmds["typescript"] = config.linters.typescript
    if config.linters.javascript:
        linter_cmds["javascript"] = config.linters.javascript

    if not linter_cmds:
        return findings

    # Group changed files by language
    files_by_lang: dict[str, list[str]] = {}
    for diff_file in diff_context.files:
        if diff_file.change_type == "deleted":
            continue
        if _is_test_path(diff_file.path):
            continue
        lang = diff_file.language
        if lang and lang in linter_cmds:
            files_by_lang.setdefault(lang, []).append(diff_file.path)

    # Run each linter on its file set
    for lang, file_paths in files_by_lang.items():
        cmd_template = linter_cmds[lang]

        # Filter to files that actually exist on disk
        existing = [f for f in file_paths if (cwd / f).exists()]
        if not existing:
            continue

        # Build command: use {files} placeholder if present, else append
        if "{files}" in cmd_template:
            cmd_str = cmd_template.replace("{files}", " ".join(shlex.quote(f) for f in existing))
            cmd_parts = shlex.split(cmd_str)
        else:
            cmd_parts = shlex.split(cmd_template) + existing

        try:
            result = _sp.run(
                cmd_parts,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                # Linter found issues — parse output into findings
                output = result.stdout.strip() or result.stderr.strip()
                # Create one finding per file with lint errors
                # (individual line-level parsing is linter-specific; keep it simple for V1)
                findings.append(GateZeroFinding(
                    check="lint",
                    severity="HIGH",
                    category="style",
                    file=", ".join(existing[:3]),
                    message=f"Linter ({cmd_template.split()[0]}) reported errors",
                    suggestion=f"Run `{cmd_template}` and fix reported issues. Output:\n{output[:500]}",
                ))
        except FileNotFoundError:
            # Linter binary not installed — warn, don't fail
            findings.append(GateZeroFinding(
                check="lint",
                severity="LOW",
                category="style",
                file="",
                message=f"Linter command not found: {cmd_template.split()[0]}",
                suggestion=f"Install {cmd_template.split()[0]} or remove from [gate_zero.linters] config",
            ))
        except _sp.TimeoutExpired:
            findings.append(GateZeroFinding(
                check="lint",
                severity="LOW",
                category="style",
                file="",
                message=f"Linter timed out after 30s: {cmd_template}",
                suggestion="Check linter configuration or increase timeout",
            ))
        except Exception:
            pass  # Don't let linter errors crash Gate Zero

    return findings


def check(diff_context: DiffContext, config: CouncilConfig, repo_root: Path | None = None) -> GateZeroResult:
    """Run all Gate Zero checks. Returns immediately — no LLM cost."""
    start = time.monotonic()
    gc = config.gate_zero
    findings: list[GateZeroFinding] = []

    if gc.check_secrets:
        findings.extend(check_secrets(diff_context))

    findings.extend(check_prompt_injection(diff_context))
    findings.extend(check_readme_updated(diff_context, gc))
    findings.extend(check_file_size(diff_context, gc))
    findings.extend(check_language_specific(diff_context, gc))
    findings.extend(check_linters(diff_context, gc, repo_root=repo_root))

    duration_ms = int((time.monotonic() - start) * 1000)

    # Hard fail if any CRITICAL findings
    hard_fail = any(f.severity == "CRITICAL" for f in findings)

    return GateZeroResult(
        passed=not hard_fail,
        hard_fail=hard_fail,
        findings=findings,
        duration_ms=duration_ms,
    )

"""Benchmark fixture validation helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_SEEDED_PR_ROOT = Path("benchmarks/seeded-prs")
VALID_VERDICTS = {"PASS", "PASS_WITH_WARNINGS", "FAIL"}
VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
VALID_CATEGORIES = {"security", "testing", "architecture", "documentation", "performance", "style"}


class BenchmarkValidationError(ValueError):
    """Raised when a seeded benchmark fixture is invalid."""


@dataclass(frozen=True)
class BenchmarkScenarioSummary:
    """Validated metadata for one seeded PR fixture."""

    scenario_id: str
    path: Path
    expected_verdict: str
    expected_findings: int
    expected_warnings: int


@dataclass(frozen=True)
class BenchmarkValidationResult:
    """Summary of validated benchmark fixtures."""

    fixtures_root: Path
    scenarios: tuple[BenchmarkScenarioSummary, ...]


def validate_seeded_pr_fixtures(
    fixtures_root: Path = DEFAULT_SEEDED_PR_ROOT,
) -> BenchmarkValidationResult:
    """Validate seeded PR fixtures and return a summary.

    Validation checks fixture shape, JSON metadata, product severity/category
    vocabulary, safe head-fixture file references, and expected finding line
    ranges. Raises BenchmarkValidationError with a sanitized user-facing
    message when a fixture is not safe or complete enough to use as benchmark
    evidence.
    """
    root = fixtures_root.resolve()
    if not root.exists():
        raise BenchmarkValidationError(f"fixtures root does not exist: {fixtures_root}")
    if not root.is_dir():
        raise BenchmarkValidationError(f"fixtures root is not a directory: {fixtures_root}")

    scenario_dirs = sorted(path for path in root.iterdir() if path.is_dir())
    if not scenario_dirs:
        raise BenchmarkValidationError(f"no seeded PR fixtures found in {fixtures_root}")

    summaries = tuple(_validate_scenario(path) for path in scenario_dirs)
    return BenchmarkValidationResult(fixtures_root=root, scenarios=summaries)


def format_benchmark_validation(result: BenchmarkValidationResult) -> list[str]:
    """Return stable human-readable lines for CLI output."""
    fixture_label = "fixture" if len(result.scenarios) == 1 else "fixtures"
    lines = [f"Validated {len(result.scenarios)} seeded PR {fixture_label}."]
    for scenario in result.scenarios:
        finding_label = "finding" if scenario.expected_findings == 1 else "findings"
        warning_label = "warning" if scenario.expected_warnings == 1 else "warnings"
        lines.append(
            "- "
            f"{scenario.scenario_id}: expected {scenario.expected_verdict}; "
            f"{scenario.expected_findings} {finding_label}; "
            f"{scenario.expected_warnings} {warning_label}"
        )
    return lines


def _validate_scenario(fixture_dir: Path) -> BenchmarkScenarioSummary:
    expected_path = fixture_dir / "expected-findings.json"
    if not expected_path.exists():
        raise BenchmarkValidationError(f"{fixture_dir.name}: missing expected-findings.json")

    expected = _load_expected_findings(expected_path, fixture_dir.name)
    scenario_id = _required_text(expected, "scenario_id", fixture_dir.name)
    if scenario_id != fixture_dir.name:
        raise BenchmarkValidationError(
            f"{fixture_dir.name}: scenario_id must match fixture directory name"
        )

    for child in ("base", "head"):
        path = fixture_dir / child
        if not path.is_dir():
            raise BenchmarkValidationError(f"{scenario_id}: missing {child}/ directory")

    expected_verdict = _required_text(expected, "expected_verdict", scenario_id)
    if expected_verdict not in VALID_VERDICTS:
        raise BenchmarkValidationError(
            f"{scenario_id}: expected_verdict must be one of {sorted(VALID_VERDICTS)}"
        )

    findings = _required_list(expected, "expected_findings", scenario_id)
    warnings = _required_list(expected, "expected_warnings", scenario_id)
    not_expected = _required_list(expected, "not_expected", scenario_id)
    if not findings and expected_verdict == "FAIL":
        raise BenchmarkValidationError(f"{scenario_id}: FAIL fixtures need expected findings")
    if not not_expected:
        raise BenchmarkValidationError(f"{scenario_id}: not_expected must not be empty")

    for index, finding in enumerate(findings, start=1):
        _validate_expected_issue(
            fixture_dir=fixture_dir,
            scenario_id=scenario_id,
            issue=finding,
            field=f"expected_findings[{index}]",
            require_lines=True,
        )

    for index, warning in enumerate(warnings, start=1):
        _validate_expected_issue(
            fixture_dir=fixture_dir,
            scenario_id=scenario_id,
            issue=warning,
            field=f"expected_warnings[{index}]",
            require_lines=False,
        )

    return BenchmarkScenarioSummary(
        scenario_id=scenario_id,
        path=fixture_dir,
        expected_verdict=expected_verdict,
        expected_findings=len(findings),
        expected_warnings=len(warnings),
    )


def _load_expected_findings(path: Path, scenario_id: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BenchmarkValidationError(
            f"{scenario_id}: expected-findings.json is invalid JSON"
        ) from exc
    if not isinstance(raw, dict):
        raise BenchmarkValidationError(f"{scenario_id}: expected-findings.json must be an object")
    return raw


def _validate_expected_issue(
    *,
    fixture_dir: Path,
    scenario_id: str,
    issue: Any,
    field: str,
    require_lines: bool,
) -> None:
    if not isinstance(issue, dict):
        raise BenchmarkValidationError(f"{scenario_id}: {field} must be an object")

    severity = _required_text(issue, "severity", f"{scenario_id}: {field}")
    if severity not in VALID_SEVERITIES:
        raise BenchmarkValidationError(
            f"{scenario_id}: {field} severity must be one of {sorted(VALID_SEVERITIES)}"
        )

    category = _required_text(issue, "category", f"{scenario_id}: {field}")
    if category not in VALID_CATEGORIES:
        raise BenchmarkValidationError(
            f"{scenario_id}: {field} category must be one of {sorted(VALID_CATEGORIES)}"
        )

    for key in ("file", "evidence"):
        _required_text(issue, key, f"{scenario_id}: {field}")

    fixture_file = _safe_head_file(fixture_dir, issue["file"], f"{scenario_id}: {field}")
    if require_lines:
        line_start = _required_int(issue, "line_start", f"{scenario_id}: {field}")
        line_end = _required_int(issue, "line_end", f"{scenario_id}: {field}")
        if line_start < 1 or line_end < line_start:
            raise BenchmarkValidationError(
                f"{scenario_id}: {field} line range must be positive and ordered"
            )
        line_count = len(fixture_file.read_text(encoding="utf-8").splitlines())
        if line_end > line_count:
            raise BenchmarkValidationError(
                f"{scenario_id}: {field} line_end exceeds head fixture length"
            )


def _safe_head_file(fixture_dir: Path, raw_file: str, field: str) -> Path:
    rel = PurePosixPath(raw_file)
    if (
        rel.is_absolute()
        or ".." in rel.parts
        or "\\" in raw_file
        or ":" in raw_file
        or raw_file.strip() != raw_file
        or not raw_file
    ):
        raise BenchmarkValidationError(f"{field} file must be a safe relative path")

    head_root = (fixture_dir / "head").resolve()
    fixture_rel = Path(*rel.parts)
    materialized = (head_root / fixture_rel.with_name(f"{fixture_rel.name}.txt")).resolve()
    if not materialized.is_relative_to(head_root):
        raise BenchmarkValidationError(f"{field} file must stay inside the head fixture")
    if not materialized.is_file():
        raise BenchmarkValidationError(f"{field} file does not exist in head fixture: {raw_file}")
    return materialized


def _required_text(data: dict[str, Any], key: str, label: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkValidationError(f"{label}: {key} must be a non-empty string")
    return value


def _required_list(data: dict[str, Any], key: str, label: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise BenchmarkValidationError(f"{label}: {key} must be a list")
    return value


def _required_int(data: dict[str, Any], key: str, label: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise BenchmarkValidationError(f"{label}: {key} must be an integer")
    return value

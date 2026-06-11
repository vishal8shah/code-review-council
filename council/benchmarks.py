"""Benchmark fixture validation helpers."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_SEEDED_PR_ROOT = Path("benchmarks/seeded-prs")
VALID_VERDICTS = {"PASS", "PASS_WITH_WARNINGS", "FAIL"}
VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
VALID_CATEGORIES = {"security", "testing", "architecture", "documentation", "performance", "style"}
SAMPLE_REPORT_CONFIDENCE = 0.98
SAMPLE_REPORT_OUTPUT_MODE = "sample"
SAMPLE_REPORT_SOURCE = "expected-findings.json"
SAMPLE_REPORT_SUGGESTION = (
    "Use this sample to understand report shape; verify fixes with a real run."
)


class BenchmarkValidationError(ValueError):
    """Raised when a seeded benchmark fixture is invalid."""


class BenchmarkScoreError(ValueError):
    """Raised when a benchmark report cannot be scored."""


class BenchmarkRunError(ValueError):
    """Raised when a seeded benchmark run cannot be prepared."""


class BenchmarkSampleReportError(ValueError):
    """Raised when an illustrative benchmark sample report cannot be written."""


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


@dataclass(frozen=True)
class BenchmarkScoreResult:
    """Score for one Council JSON report against one seeded fixture."""

    scenario_id: str
    passed: bool
    expected_verdict: str
    report_verdict: str
    expected_findings: int
    matched_findings: int
    expected_warnings: int
    matched_warnings: int
    missed: tuple[str, ...]
    degraded: bool
    degraded_reasons: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkPreparedRun:
    """Prepared throwaway repository for one seeded benchmark run."""

    scenario_id: str
    run_dir: Path
    base_branch: str
    head_branch: str
    report_path: Path
    review_command: str
    score_command: str


@dataclass(frozen=True)
class BenchmarkSampleReport:
    """Illustrative Council JSON report generated from fixture expectations."""

    scenario_id: str
    output_path: Path


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


def score_benchmark_report(fixture_dir: Path, report_path: Path) -> BenchmarkScoreResult:
    """Score a Council JSON report against one validated seeded PR fixture.

    The score passes only when the report verdict equals the fixture's expected
    verdict and every expected blocker/warning has a one-to-one match in the
    correct report bucket. Matching always requires file, category, and
    severity; it also requires policy id and exact line range when the fixture
    expectation declares those fields. Raises BenchmarkValidationError for
    invalid fixture metadata and BenchmarkScoreError for missing, malformed, or
    structurally invalid report JSON.
    """
    _validate_scenario(fixture_dir)
    expected = _load_expected_findings(fixture_dir / "expected-findings.json", fixture_dir.name)
    report = _load_report(report_path)

    report_verdict = _report_verdict(report, report_path)
    accepted_blockers = _report_issue_list(report, "accepted_blockers", report_path)
    warnings = _report_issue_list(report, "warnings", report_path)

    missed: list[str] = []
    expected_verdict = expected["expected_verdict"]
    if report_verdict != expected_verdict:
        missed.append(f"expected verdict {expected_verdict}, got {report_verdict}")

    matched_findings = _count_matches(
        expected["expected_findings"],
        accepted_blockers,
        missed=missed,
        label="expected finding",
    )
    matched_warnings = _count_matches(
        expected["expected_warnings"],
        warnings,
        missed=missed,
        label="expected warning",
    )

    degraded = report.get("degraded", False)
    if not isinstance(degraded, bool):
        raise BenchmarkScoreError(f"{report_path}: degraded must be a boolean when present")
    degraded_reasons = _report_degraded_reasons(report, report_path)

    return BenchmarkScoreResult(
        scenario_id=expected["scenario_id"],
        passed=not missed,
        expected_verdict=expected_verdict,
        report_verdict=report_verdict,
        expected_findings=len(expected["expected_findings"]),
        matched_findings=matched_findings,
        expected_warnings=len(expected["expected_warnings"]),
        matched_warnings=matched_warnings,
        missed=tuple(missed),
        degraded=degraded,
        degraded_reasons=tuple(degraded_reasons),
    )


def write_sample_benchmark_report(
    fixture_dir: Path,
    output_path: Path,
    *,
    overwrite: bool = False,
    base_dir: Path | None = None,
) -> BenchmarkSampleReport:
    """Write an illustrative Council JSON report from fixture expectations.

    The sample report is for onboarding and score-command demos only. It is not
    model-run benchmark evidence.

    Args:
        fixture_dir: Seeded PR fixture directory containing
            ``expected-findings.json``.
        output_path: JSON file to write. Relative paths resolve against
            ``base_dir`` when supplied, otherwise the current working directory.
        overwrite: When false, refuse to replace an existing file.
        base_dir: Optional base directory for relative output paths.

    Returns:
        A ``BenchmarkSampleReport`` with the scenario id and resolved output
        path.

    Raises:
        BenchmarkValidationError: If fixture metadata is invalid.
        BenchmarkSampleReportError: If the output path is an existing directory
            or existing file without ``overwrite=True``, if the output path uses
            a symlink, or if the file cannot be written.
    """
    scenario, expected = _load_validated_sample_fixture(fixture_dir)
    path = _resolve_sample_output_path(output_path, overwrite=overwrite, base_dir=base_dir)
    _write_sample_report_json(path, _sample_report_from_expected(expected), overwrite=overwrite)
    return _sample_report_result(scenario, output_path=path)


def prepare_benchmark_run(
    fixture_dir: Path,
    output_dir: Path,
    *,
    base_branch: str = "main",
    head_branch: str = "benchmark-head",
) -> BenchmarkPreparedRun:
    """Materialize a seeded fixture into a throwaway git repository.

    The prepared repository contains a committed safe base branch and a checked
    out head branch with the risky fixture changes applied. It does not call a
    model or run Council; callers use the returned commands to run and score a
    real review when model credentials are available.
    """
    scenario = _validate_scenario(fixture_dir)
    run_dir = output_dir.resolve()
    if run_dir.exists() and any(run_dir.iterdir()):
        raise BenchmarkRunError(f"{output_dir}: output directory already exists and is not empty")
    run_dir.mkdir(parents=True, exist_ok=True)

    _materialize_fixture_tree(fixture_dir / "base", run_dir)
    _run_git(["init"], cwd=run_dir)
    _run_git(["checkout", "-b", base_branch], cwd=run_dir)
    _run_git(["config", "user.email", "council-benchmark@example.invalid"], cwd=run_dir)
    _run_git(["config", "user.name", "Code Review Council Benchmark"], cwd=run_dir)
    _run_git(["add", "."], cwd=run_dir)
    _run_git(["commit", "-m", "seed benchmark base"], cwd=run_dir)
    _run_git(["checkout", "-b", head_branch], cwd=run_dir)
    _materialize_fixture_tree(fixture_dir / "head", run_dir)

    report_path = run_dir / "council-report.json"
    return BenchmarkPreparedRun(
        scenario_id=scenario.scenario_id,
        run_dir=run_dir,
        base_branch=base_branch,
        head_branch=head_branch,
        report_path=report_path,
        review_command=(
            f"council review --repo \"{run_dir}\" --branch {base_branch} "
            f"--output-json \"{report_path}\""
        ),
        score_command=(
            f"council benchmarks score --fixture \"{fixture_dir.resolve()}\" "
            f"--report \"{report_path}\""
        ),
    )


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


def format_prepared_benchmark_run(result: BenchmarkPreparedRun) -> list[str]:
    """Return stable human-readable lines for a prepared benchmark run."""
    return [
        f"{result.scenario_id}: prepared run repository",
        f"- run directory: {result.run_dir}",
        f"- base branch: {result.base_branch}",
        f"- head branch: {result.head_branch}",
        f"- review command: {result.review_command}",
        f"- score command: {result.score_command}",
    ]


def format_sample_benchmark_report(result: BenchmarkSampleReport) -> list[str]:
    """Return stable human-readable lines for a sample report."""
    return [
        f"{result.scenario_id}: wrote illustrative sample report",
        f"- output: {result.output_path}",
        "- note: sample reports are not model-run benchmark evidence",
    ]


def format_benchmark_score(result: BenchmarkScoreResult) -> list[str]:
    """Return stable human-readable score lines for CLI output."""
    status = "PASS" if result.passed else "FAIL"
    lines = [
        f"{result.scenario_id}: {status}",
        f"- verdict: expected {result.expected_verdict}; report {result.report_verdict}",
        f"- findings: {result.matched_findings}/{result.expected_findings} expected blockers matched",
        f"- warnings: {result.matched_warnings}/{result.expected_warnings} expected warnings matched",
    ]
    if result.degraded:
        reason_count = len(result.degraded_reasons)
        lines.append(f"- degraded: true ({reason_count} reasons)")
    if result.missed:
        lines.append("- missed expectations:")
        lines.extend(f"  - {item}" for item in result.missed)
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


def _load_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BenchmarkScoreError(f"{path}: report file does not exist")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BenchmarkScoreError(f"{path}: report is invalid JSON") from exc
    if not isinstance(raw, dict):
        raise BenchmarkScoreError(f"{path}: report JSON must be an object")
    return raw


def _load_validated_sample_fixture(
    fixture_dir: Path,
) -> tuple[BenchmarkScenarioSummary, dict[str, Any]]:
    """Validate one sample fixture and load its expected-findings payload."""
    scenario = _validate_scenario(fixture_dir)
    expected = _load_expected_findings(fixture_dir / "expected-findings.json", scenario.scenario_id)
    return scenario, expected


def _resolve_sample_output_path(
    output_path: Path,
    *,
    overwrite: bool,
    base_dir: Path | None,
) -> Path:
    """Resolve a sample output path and reject unsafe or conflicting targets."""
    root = Path.cwd() if base_dir is None else base_dir
    raw_path = output_path if output_path.is_absolute() else root / output_path
    if _has_symlink_component(raw_path):
        raise BenchmarkSampleReportError(f"{output_path}: output path must not use symlinks")
    path = raw_path.resolve()
    if path.exists() and path.is_dir():
        raise BenchmarkSampleReportError(f"{output_path}: output path is a directory")
    if path.exists() and not overwrite:
        raise BenchmarkSampleReportError(f"{output_path}: output file already exists")
    return path


def _has_symlink_component(path: Path) -> bool:
    """Return true when the path or any existing parent is a symlink."""
    return path.is_symlink() or any(parent.exists() and parent.is_symlink() for parent in path.parents)


def _write_sample_report_json(path: Path, report: dict[str, Any], *, overwrite: bool) -> None:
    """Write sample JSON without following a late-created output symlink."""
    payload = json.dumps(report, indent=2) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if _has_symlink_component(path):
            raise BenchmarkSampleReportError(f"{path}: output path must not use symlinks")
        if not overwrite:
            with path.open("x", encoding="utf-8") as file:
                file.write(payload)
            return
        _replace_sample_report_json(path, payload)
    except OSError as exc:
        raise BenchmarkSampleReportError(f"{path}: could not write sample report") from exc


def _replace_sample_report_json(path: Path, payload: str) -> None:
    """Atomically replace an existing sample report target."""
    if _has_symlink_component(path):
        raise BenchmarkSampleReportError(f"{path}: output path must not use symlinks")

    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as temp_file:
            temp_file.write(payload)
            temp_name = temp_file.name
        if _has_symlink_component(path):
            raise BenchmarkSampleReportError(f"{path}: output path must not use symlinks")
        Path(temp_name).replace(path)
    finally:
        if temp_name is not None:
            temp_path = Path(temp_name)
            if temp_path.exists():
                with suppress(OSError):
                    temp_path.unlink()


def _sample_report_result(
    scenario: BenchmarkScenarioSummary,
    *,
    output_path: Path,
) -> BenchmarkSampleReport:
    return BenchmarkSampleReport(
        scenario_id=scenario.scenario_id,
        output_path=output_path,
    )


def _sample_report_from_expected(expected: dict[str, Any]) -> dict[str, Any]:
    """Map fixture expectations into the illustrative Council JSON shape.

    Expected blockers become ``accepted_blockers`` and expected warnings become
    ``warnings`` so the normal benchmark score command can validate the sample
    report. Required metadata is read through validation helpers so malformed
    fixtures fail with benchmark-specific errors instead of raw ``KeyError`` or
    ``TypeError`` exceptions.
    """
    scenario_id = _required_text(expected, "scenario_id", "sample report")
    expected_verdict = _required_text(expected, "expected_verdict", scenario_id)
    expected_findings = _required_list(expected, "expected_findings", scenario_id)
    expected_warnings = _required_list(expected, "expected_warnings", scenario_id)
    return {
        "verdict": expected_verdict,
        "confidence": SAMPLE_REPORT_CONFIDENCE,
        "chair_output_mode": SAMPLE_REPORT_OUTPUT_MODE,
        "degraded": False,
        "degraded_reasons": [],
        "summary": (
            f"Illustrative benchmark report for {scenario_id}. "
            "Generated from expected fixture findings, not a model run."
        ),
        "rationale": (
            "This sample shows the JSON fields that benchmark scoring expects. "
            "Run Council against the prepared fixture repo for real benchmark evidence."
        ),
        "accepted_blockers": [
            _sample_issue(issue, chair_action="accepted")
            for issue in expected_findings
        ],
        "warnings": [
            _sample_issue(issue, chair_action="accepted")
            for issue in expected_warnings
        ],
        "dismissed_findings": [],
        "benchmark_sample": {
            "scenario_id": scenario_id,
            "source": SAMPLE_REPORT_SOURCE,
            "model_run": False,
        },
    }


def _sample_issue(issue: Any, *, chair_action: str) -> dict[str, Any]:
    if not isinstance(issue, dict):
        raise BenchmarkValidationError("sample issue must be an object")
    sample = {
        "severity": _required_text(issue, "severity", "sample issue"),
        "category": _required_text(issue, "category", "sample issue"),
        "file": _required_text(issue, "file", "sample issue"),
        "description": _required_text(issue, "evidence", "sample issue"),
        "suggestion": SAMPLE_REPORT_SUGGESTION,
        "chair_action": chair_action,
    }
    for key in ("line_start", "line_end", "policy_id"):
        if key in issue:
            sample[key] = issue[key]
    return sample


def _materialize_fixture_tree(source_root: Path, output_root: Path) -> None:
    root = source_root.resolve()
    target_root = output_root.resolve()
    if not root.is_dir():
        raise BenchmarkRunError(f"{source_root}: fixture tree does not exist")
    for source in sorted(path for path in root.rglob("*") if path.is_file()):
        relative = source.relative_to(root)
        target = (target_root / _materialized_relative_path(relative)).resolve()
        if not target.is_relative_to(target_root):
            raise BenchmarkRunError(f"{source}: materialized path escapes output directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _materialized_relative_path(relative: Path) -> Path:
    if relative.suffix == ".txt":
        return relative.with_suffix("")
    return relative


def _run_git(args: list[str], *, cwd: Path) -> None:
    try:
        subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = (getattr(exc, "stderr", "") or str(exc)).strip()
        detail = detail.splitlines()[0] if detail else "no detail"
        detail = detail[:300]
        raise BenchmarkRunError(f"git {' '.join(args)} failed: {detail.strip()}") from exc


def _report_verdict(report: dict[str, Any], report_path: Path) -> str:
    verdict = report.get("verdict")
    if verdict not in VALID_VERDICTS:
        raise BenchmarkScoreError(f"{report_path}: verdict must be one of {sorted(VALID_VERDICTS)}")
    return verdict


def _report_issue_list(report: dict[str, Any], key: str, report_path: Path) -> list[dict[str, Any]]:
    raw = report.get(key)
    if not isinstance(raw, list):
        raise BenchmarkScoreError(f"{report_path}: {key} must be a list")
    if not all(isinstance(item, dict) for item in raw):
        raise BenchmarkScoreError(f"{report_path}: {key} entries must be objects")
    return raw


def _report_degraded_reasons(report: dict[str, Any], report_path: Path) -> list[str]:
    raw = report.get("degraded_reasons", [])
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise BenchmarkScoreError(f"{report_path}: degraded_reasons must be a list of strings")
    return raw


def _count_matches(
    expected_items: list[Any],
    actual_items: list[dict[str, Any]],
    *,
    missed: list[str],
    label: str,
) -> int:
    matched = 0
    consumed: set[int] = set()
    for expected in expected_items:
        match_index = next(
            (
                index
                for index, actual in enumerate(actual_items)
                if index not in consumed and _issue_matches(expected, actual)
            ),
            None,
        )
        if match_index is not None:
            consumed.add(match_index)
            matched += 1
        else:
            missed.append(
                f"{label} not matched: "
                f"{expected['severity']} {expected['category']} in {expected['file']}"
            )
    return matched


def _issue_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    required_keys = ["file", "category", "severity"]
    if "policy_id" in expected:
        required_keys.append("policy_id")
    if "line_start" in expected:
        required_keys.append("line_start")
    if "line_end" in expected:
        required_keys.append("line_end")
    return all(actual.get(key) == expected[key] for key in required_keys)


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

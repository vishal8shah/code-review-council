from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from council.benchmarks import (
    BenchmarkRunError,
    BenchmarkScoreError,
    BenchmarkValidationError,
    prepare_benchmark_run,
    score_benchmark_report,
    validate_seeded_pr_fixtures,
)
from council.cli import app


FIXTURE_ROOT = Path("benchmarks/seeded-prs")


def _copy_fixture(tmp_path: Path) -> Path:
    fixture_root = tmp_path / "seeded-prs"
    shutil.copytree(FIXTURE_ROOT / "agentic-login-bypass", fixture_root / "agentic-login-bypass")
    return fixture_root


def _expected_path(fixture_root: Path) -> Path:
    return fixture_root / "agentic-login-bypass" / "expected-findings.json"


def _load_expected(fixture_root: Path) -> dict:
    return json.loads(_expected_path(fixture_root).read_text(encoding="utf-8"))


def _write_expected(fixture_root: Path, expected: dict) -> None:
    _expected_path(fixture_root).write_text(json.dumps(expected), encoding="utf-8")


def _write_report(tmp_path: Path, **overrides) -> Path:
    report = {
        "verdict": "FAIL",
        "confidence": 0.91,
        "degraded": False,
        "degraded_reasons": [],
        "accepted_blockers": [
            {
                "severity": "HIGH",
                "category": "security",
                "file": "src/billing/access.py",
                "line_start": 25,
                "line_end": 27,
                "description": "Authorization bypass through request user_id.",
                "suggestion": "Use the authenticated user id.",
                "policy_id": "SEC-AUTHZ-001",
                "chair_action": "accepted",
            }
        ],
        "warnings": [
            {
                "severity": "MEDIUM",
                "category": "testing",
                "file": "tests/access_test_sample.py",
                "description": "Missing forged user_id regression test.",
                "suggestion": "Add coverage for attacker controlled user_id.",
                "chair_action": "accepted",
            }
        ],
        "dismissed_findings": [],
    }
    report.update(overrides)
    path = tmp_path / "council-report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def test_validate_seeded_pr_fixtures_accepts_current_fixture():
    result = validate_seeded_pr_fixtures(FIXTURE_ROOT)

    assert len(result.scenarios) == 1
    scenario = result.scenarios[0]
    assert scenario.scenario_id == "agentic-login-bypass"
    assert scenario.expected_verdict == "FAIL"
    assert scenario.expected_findings == 1
    assert scenario.expected_warnings == 1


def test_benchmarks_validate_cli_reports_current_fixture():
    result = CliRunner().invoke(app, ["benchmarks", "validate", "--repo", str(Path.cwd())])

    assert result.exit_code == 0
    assert "Council Benchmark Fixtures" in result.output
    assert "Validated 1 seeded PR fixture." in result.output
    assert "agentic-login-bypass: expected FAIL; 1 finding; 1 warning" in result.output
    assert "OK" in result.output


def test_score_benchmark_report_matches_expected_fixture(tmp_path):
    report_path = _write_report(tmp_path)

    result = score_benchmark_report(FIXTURE_ROOT / "agentic-login-bypass", report_path)

    assert result.passed is True
    assert result.expected_verdict == "FAIL"
    assert result.report_verdict == "FAIL"
    assert result.matched_findings == 1
    assert result.matched_warnings == 1
    assert result.missed == ()


def test_benchmarks_score_cli_reports_pass(tmp_path):
    report_path = _write_report(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "benchmarks",
            "score",
            "--fixture",
            str(FIXTURE_ROOT / "agentic-login-bypass"),
            "--report",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert "Council Benchmark Score" in result.output
    assert "agentic-login-bypass: PASS" in result.output
    assert "findings: 1/1 expected blockers matched" in result.output
    assert "warnings: 1/1 expected warnings matched" in result.output


def test_prepare_benchmark_run_materializes_throwaway_git_repo(tmp_path):
    output_dir = tmp_path / "run"

    result = prepare_benchmark_run(FIXTURE_ROOT / "agentic-login-bypass", output_dir)

    assert result.scenario_id == "agentic-login-bypass"
    assert result.base_branch == "main"
    assert result.head_branch == "benchmark-head"
    assert (output_dir / ".git").is_dir()
    assert (output_dir / "src" / "billing" / "access.py").is_file()
    assert not (output_dir / "src" / "billing" / "access.py.txt").exists()
    assert 'request_params.get("user_id")' in (
        output_dir / "src" / "billing" / "access.py"
    ).read_text(encoding="utf-8")
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"],
        cwd=output_dir,
        text=True,
    ).strip()
    status = subprocess.check_output(["git", "status", "--short"], cwd=output_dir, text=True)
    assert branch == "benchmark-head"
    assert "src/billing/access.py" in status
    assert "council review" in result.review_command
    assert "council benchmarks score" in result.score_command


def test_prepare_benchmark_run_refuses_non_empty_output_dir(tmp_path):
    output_dir = tmp_path / "run"
    output_dir.mkdir()
    (output_dir / "existing.txt").write_text("keep me", encoding="utf-8")

    with pytest.raises(BenchmarkRunError, match="not empty"):
        prepare_benchmark_run(FIXTURE_ROOT / "agentic-login-bypass", output_dir)


def test_benchmarks_prepare_run_cli_reports_commands(tmp_path):
    output_dir = tmp_path / "prepared"

    result = CliRunner().invoke(
        app,
        [
            "benchmarks",
            "prepare-run",
            "--fixture",
            str(FIXTURE_ROOT / "agentic-login-bypass"),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert "Council Benchmark Run" in result.output
    assert "agentic-login-bypass: prepared run repository" in result.output
    assert "review command:" in result.output
    assert "score command:" in result.output


def test_benchmarks_score_cli_fails_for_missing_expected_blocker(tmp_path):
    report_path = _write_report(tmp_path, accepted_blockers=[])

    result = CliRunner().invoke(
        app,
        [
            "benchmarks",
            "score",
            "--fixture",
            str(FIXTURE_ROOT / "agentic-login-bypass"),
            "--report",
            str(report_path),
        ],
    )

    assert result.exit_code == 1
    assert "agentic-login-bypass: FAIL" in result.output
    assert "expected finding not matched" in result.output


def test_score_benchmark_report_fails_for_wrong_verdict(tmp_path):
    report_path = _write_report(tmp_path, verdict="PASS", accepted_blockers=[])

    result = score_benchmark_report(FIXTURE_ROOT / "agentic-login-bypass", report_path)

    assert result.passed is False
    assert "expected verdict FAIL, got PASS" in result.missed


def test_score_benchmark_report_does_not_reuse_one_actual_for_two_expected_items(tmp_path):
    fixture_root = _copy_fixture(tmp_path)
    expected = _load_expected(fixture_root)
    expected["expected_findings"].append(expected["expected_findings"][0].copy())
    _write_expected(fixture_root, expected)
    report_path = _write_report(tmp_path)

    result = score_benchmark_report(fixture_root / "agentic-login-bypass", report_path)

    assert result.passed is False
    assert result.matched_findings == 1
    assert result.expected_findings == 2
    assert any("expected finding not matched" in item for item in result.missed)


def test_score_benchmark_report_requires_expected_line_identity(tmp_path):
    report_path = _write_report(
        tmp_path,
        accepted_blockers=[
            {
                "severity": "HIGH",
                "category": "security",
                "file": "src/billing/access.py",
                "line_start": 12,
                "line_end": 13,
                "description": "Different security issue in the same file.",
                "policy_id": "SEC-AUTHZ-001",
                "chair_action": "accepted",
            }
        ],
    )

    result = score_benchmark_report(FIXTURE_ROOT / "agentic-login-bypass", report_path)

    assert result.passed is False
    assert result.matched_findings == 0


def test_benchmarks_score_cli_surfaces_degraded_report(tmp_path):
    report_path = _write_report(
        tmp_path,
        degraded=True,
        degraded_reasons=["secops: timeout"],
    )

    result = CliRunner().invoke(
        app,
        [
            "benchmarks",
            "score",
            "--fixture",
            str(FIXTURE_ROOT / "agentic-login-bypass"),
            "--report",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert "degraded: true (1 reasons)" in result.output


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{", "invalid JSON"),
        ("[]", "report JSON must be an object"),
    ],
)
def test_score_benchmark_report_rejects_malformed_report(tmp_path, content, message):
    report_path = tmp_path / "council-report.json"
    report_path.write_text(content, encoding="utf-8")

    with pytest.raises(BenchmarkScoreError, match=message):
        score_benchmark_report(FIXTURE_ROOT / "agentic-login-bypass", report_path)


def test_score_benchmark_report_rejects_missing_report_file(tmp_path):
    with pytest.raises(BenchmarkScoreError, match="report file does not exist"):
        score_benchmark_report(
            FIXTURE_ROOT / "agentic-login-bypass",
            tmp_path / "missing-report.json",
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"verdict": "MAYBE"}, "verdict must be one of"),
        ({"accepted_blockers": {}}, "accepted_blockers must be a list"),
        ({"warnings": ["bad"]}, "warnings entries must be objects"),
        ({"degraded": "false"}, "degraded must be a boolean"),
        ({"degraded_reasons": ["ok", 123]}, "degraded_reasons must be a list of strings"),
    ],
)
def test_score_benchmark_report_rejects_bad_report_shape(tmp_path, overrides, message):
    report_path = _write_report(tmp_path, **overrides)

    with pytest.raises(BenchmarkScoreError, match=message):
        score_benchmark_report(FIXTURE_ROOT / "agentic-login-bypass", report_path)


def test_validate_seeded_pr_fixtures_rejects_missing_root(tmp_path):
    with pytest.raises(BenchmarkValidationError, match="fixtures root does not exist"):
        validate_seeded_pr_fixtures(tmp_path / "missing")


def test_validate_seeded_pr_fixtures_rejects_non_directory_root(tmp_path):
    root_file = tmp_path / "seeded-prs"
    root_file.write_text("not a directory", encoding="utf-8")

    with pytest.raises(BenchmarkValidationError, match="not a directory"):
        validate_seeded_pr_fixtures(root_file)


def test_validate_seeded_pr_fixtures_rejects_empty_root(tmp_path):
    fixture_root = tmp_path / "seeded-prs"
    fixture_root.mkdir()

    with pytest.raises(BenchmarkValidationError, match="no seeded PR fixtures"):
        validate_seeded_pr_fixtures(fixture_root)


@pytest.mark.parametrize("raw_json", ["{", "[]"])
def test_validate_seeded_pr_fixtures_rejects_malformed_expected_json(tmp_path, raw_json):
    fixture_root = _copy_fixture(tmp_path)
    _expected_path(fixture_root).write_text(raw_json, encoding="utf-8")

    with pytest.raises(BenchmarkValidationError):
        validate_seeded_pr_fixtures(fixture_root)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda expected: expected.update({"scenario_id": "different"}), "scenario_id must match"),
        (lambda expected: expected.update({"expected_verdict": "MAYBE"}), "expected_verdict"),
        (lambda expected: expected.update({"expected_findings": []}), "FAIL fixtures need"),
        (lambda expected: expected.update({"not_expected": []}), "not_expected must not be empty"),
    ],
)
def test_validate_seeded_pr_fixtures_rejects_scenario_invariants(
    tmp_path,
    mutate,
    message,
):
    fixture_root = _copy_fixture(tmp_path)
    expected = _load_expected(fixture_root)
    mutate(expected)
    _write_expected(fixture_root, expected)

    with pytest.raises(BenchmarkValidationError, match=message):
        validate_seeded_pr_fixtures(fixture_root)


@pytest.mark.parametrize("directory", ["base", "head"])
def test_validate_seeded_pr_fixtures_rejects_missing_fixture_directory(tmp_path, directory):
    fixture_root = _copy_fixture(tmp_path)
    shutil.rmtree(fixture_root / "agentic-login-bypass" / directory)

    with pytest.raises(BenchmarkValidationError, match=f"missing {directory}/ directory"):
        validate_seeded_pr_fixtures(fixture_root)


@pytest.mark.parametrize("unsafe_file", ["../outside", "src\\billing\\access.py", "C:/outside"])
def test_validate_seeded_pr_fixtures_rejects_unsafe_file_paths(tmp_path, unsafe_file):
    fixture_root = _copy_fixture(tmp_path)
    expected = _load_expected(fixture_root)
    expected["expected_findings"][0]["file"] = unsafe_file
    _write_expected(fixture_root, expected)

    with pytest.raises(BenchmarkValidationError, match="safe relative path"):
        validate_seeded_pr_fixtures(fixture_root)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("severity", "BLOCKER", "severity must be one of"),
        ("category", "security-ish", "category must be one of"),
    ],
)
def test_validate_seeded_pr_fixtures_rejects_invalid_issue_vocabulary(
    tmp_path,
    field,
    value,
    message,
):
    fixture_root = _copy_fixture(tmp_path)
    expected = _load_expected(fixture_root)
    expected["expected_findings"][0][field] = value
    _write_expected(fixture_root, expected)

    with pytest.raises(BenchmarkValidationError, match=message):
        validate_seeded_pr_fixtures(fixture_root)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"line_start": "1"}, "line_start must be an integer"),
        ({"line_start": 0}, "line range must be positive"),
        ({"line_start": 30, "line_end": 20}, "line range must be positive"),
        ({"line_end": 999}, "line_end exceeds"),
    ],
)
def test_validate_seeded_pr_fixtures_rejects_invalid_line_ranges(
    tmp_path,
    updates,
    message,
):
    fixture_root = _copy_fixture(tmp_path)
    expected = _load_expected(fixture_root)
    expected["expected_findings"][0].update(updates)
    _write_expected(fixture_root, expected)

    with pytest.raises(BenchmarkValidationError, match=message):
        validate_seeded_pr_fixtures(fixture_root)


def test_benchmarks_validate_cli_fails_for_missing_head_evidence(tmp_path):
    fixture_root = _copy_fixture(tmp_path)
    expected = _load_expected(fixture_root)
    expected["expected_findings"][0]["file"] = "src/billing/missing.py"
    _write_expected(fixture_root, expected)

    result = CliRunner().invoke(
        app,
        ["benchmarks", "validate", "--fixtures-root", str(fixture_root)],
    )

    assert result.exit_code == 1
    assert "Benchmark validation failed" in result.output
    assert "does not exist in head fixture" in result.output

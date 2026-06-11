from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

import council.benchmarks as benchmarks
from council.benchmarks import (
    BenchmarkRunError,
    BenchmarkSampleReportError,
    BenchmarkScoreError,
    BenchmarkValidationError,
    prepare_benchmark_run,
    score_benchmark_report,
    validate_seeded_pr_fixtures,
    write_sample_benchmark_report,
)
from council.cli import _benchmark_score_command, _shell_quote_path, app


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
    assert result.sample_report is False


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
    assert "evidence: Council report; scorer does not verify model provenance" in result.output


def test_benchmarks_score_cli_labels_sample_reports(tmp_path):
    report_path = tmp_path / "sample-report.json"
    write_sample_benchmark_report(FIXTURE_ROOT / "agentic-login-bypass", report_path)

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
    assert "agentic-login-bypass: PASS" in result.output
    assert "evidence: illustrative sample report; not model-run benchmark evidence" in result.output


def test_score_benchmark_report_rejects_malformed_sample_metadata(tmp_path):
    report_path = _write_report(
        tmp_path,
        benchmark_sample={"scenario_id": "agentic-login-bypass", "model_run": "false"},
    )

    with pytest.raises(BenchmarkScoreError, match="benchmark_sample.model_run"):
        score_benchmark_report(FIXTURE_ROOT / "agentic-login-bypass", report_path)


def test_score_benchmark_report_rejects_non_object_sample_metadata(tmp_path):
    report_path = _write_report(tmp_path, benchmark_sample="sample")

    with pytest.raises(BenchmarkScoreError, match="benchmark_sample must be an object"):
        score_benchmark_report(FIXTURE_ROOT / "agentic-login-bypass", report_path)


def test_score_benchmark_report_rejects_sample_metadata_without_model_run(tmp_path):
    report_path = _write_report(
        tmp_path,
        benchmark_sample={"scenario_id": "agentic-login-bypass"},
    )

    with pytest.raises(BenchmarkScoreError, match="benchmark_sample.model_run"):
        score_benchmark_report(FIXTURE_ROOT / "agentic-login-bypass", report_path)


def test_score_benchmark_report_treats_model_run_metadata_as_non_sample(tmp_path):
    report_path = _write_report(
        tmp_path,
        benchmark_sample={"scenario_id": "agentic-login-bypass", "model_run": True},
    )

    result = score_benchmark_report(FIXTURE_ROOT / "agentic-login-bypass", report_path)

    assert result.sample_report is False


def test_shell_quote_path_handles_spaces_and_quotes():
    quoted = _shell_quote_path(Path("owner's sample report;.json"))

    if os.name == "nt":
        assert quoted == "\"owner's sample report;.json\""
    else:
        assert quoted == """'owner'\"'\"'s sample report;.json'"""


def test_benchmark_score_command_resolves_fixture_and_report_paths(tmp_path):
    fixture_path = tmp_path / "fixture path"
    report_path = tmp_path / "reports" / "sample report.json"

    command = _benchmark_score_command(fixture_path=fixture_path, report_path=report_path)

    assert str(fixture_path.resolve()) in command
    assert str(report_path.resolve()) in command


def test_write_sample_benchmark_report_can_be_scored(tmp_path):
    report_path = tmp_path / "sample-report.json"

    sample = write_sample_benchmark_report(
        FIXTURE_ROOT / "agentic-login-bypass",
        report_path,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    score = score_benchmark_report(FIXTURE_ROOT / "agentic-login-bypass", report_path)

    assert sample.scenario_id == "agentic-login-bypass"
    assert sample.output_path == report_path
    assert report["chair_output_mode"] == "sample"
    assert report["benchmark_sample"]["model_run"] is False
    assert report["dismissed_findings"] == []
    blocker = report["accepted_blockers"][0]
    warning = report["warnings"][0]
    assert blocker["severity"] == "HIGH"
    assert blocker["category"] == "security"
    assert blocker["file"] == "src/billing/access.py"
    assert blocker["line_start"] == 25
    assert blocker["line_end"] == 27
    assert blocker["policy_id"] == "SEC-AUTHZ-001"
    assert blocker["chair_action"] == "accepted"
    assert "untrusted parameter" in blocker["description"]
    assert warning["severity"] == "MEDIUM"
    assert warning["category"] == "testing"
    assert warning["file"] == "tests/access_test_sample.py"
    assert warning["chair_action"] == "accepted"
    assert "attacker-controlled user_id" in warning["description"]
    assert score.passed is True


def test_write_sample_benchmark_report_returns_resolved_output_path(tmp_path, monkeypatch):
    fixture_dir = (
        Path(__file__).resolve().parents[1] / FIXTURE_ROOT / "agentic-login-bypass"
    ).resolve()
    monkeypatch.chdir(tmp_path)

    sample = write_sample_benchmark_report(
        fixture_dir,
        Path("sample-report.json"),
    )

    assert sample.output_path == tmp_path / "sample-report.json"
    assert sample.output_path.is_absolute()


def test_write_sample_benchmark_report_resolves_relative_output_from_base_dir(tmp_path):
    report_path = Path("reports/sample-report.json")

    sample = write_sample_benchmark_report(
        FIXTURE_ROOT / "agentic-login-bypass",
        report_path,
        base_dir=tmp_path,
    )

    assert sample.output_path == (tmp_path / report_path).resolve()
    assert sample.output_path.is_file()


def test_write_sample_benchmark_report_rejects_relative_output_outside_base_dir(tmp_path):
    outside_path = tmp_path.parent / "sample-report-outside.json"

    with pytest.raises(BenchmarkSampleReportError, match="relative output path must stay under"):
        write_sample_benchmark_report(
            FIXTURE_ROOT / "agentic-login-bypass",
            Path("../sample-report-outside.json"),
            base_dir=tmp_path,
        )

    assert not outside_path.exists()


def test_write_sample_benchmark_report_accepts_normalized_relative_output_inside_base_dir(tmp_path):
    report_path = Path("reports/../sample-report.json")

    sample = write_sample_benchmark_report(
        FIXTURE_ROOT / "agentic-login-bypass",
        report_path,
        base_dir=tmp_path,
    )

    assert sample.output_path == (tmp_path / "sample-report.json").resolve()
    assert sample.output_path.is_file()


def test_write_sample_benchmark_report_resolves_symlinked_base_dir(tmp_path):
    real_base = tmp_path / "real-base"
    real_base.mkdir()
    linked_base = tmp_path / "linked-base"
    try:
        linked_base.symlink_to(real_base, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    sample = write_sample_benchmark_report(
        FIXTURE_ROOT / "agentic-login-bypass",
        Path("reports/sample-report.json"),
        base_dir=linked_base,
    )

    assert sample.output_path == (real_base / "reports" / "sample-report.json").resolve()
    assert sample.output_path.is_file()


def test_write_sample_benchmark_report_handles_empty_pass_expectations(tmp_path):
    fixture_root = _copy_fixture(tmp_path)
    expected = _load_expected(fixture_root)
    expected["expected_verdict"] = "PASS"
    expected["expected_findings"] = []
    expected["expected_warnings"] = []
    _write_expected(fixture_root, expected)
    report_path = tmp_path / "sample-report.json"

    write_sample_benchmark_report(fixture_root / "agentic-login-bypass", report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    score = score_benchmark_report(fixture_root / "agentic-login-bypass", report_path)

    assert report["verdict"] == "PASS"
    assert report["accepted_blockers"] == []
    assert report["warnings"] == []
    assert score.passed is True


def test_write_sample_benchmark_report_refuses_overwrite(tmp_path):
    report_path = tmp_path / "sample-report.json"
    report_path.write_text("keep me", encoding="utf-8")

    with pytest.raises(BenchmarkSampleReportError, match="already exists"):
        write_sample_benchmark_report(FIXTURE_ROOT / "agentic-login-bypass", report_path)


def test_write_sample_benchmark_report_overwrites_when_requested(tmp_path):
    report_path = tmp_path / "sample-report.json"
    report_path.write_text("replace me", encoding="utf-8")

    write_sample_benchmark_report(
        FIXTURE_ROOT / "agentic-login-bypass",
        report_path,
        overwrite=True,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["benchmark_sample"]["model_run"] is False
    assert "replace me" not in report_path.read_text(encoding="utf-8")
    assert list(tmp_path.glob(".sample-report.json.*.tmp")) == []


def test_write_sample_benchmark_report_rejects_directory_output(tmp_path):
    output_dir = tmp_path / "sample-report.json"
    output_dir.mkdir()

    with pytest.raises(BenchmarkSampleReportError, match="output path is a directory"):
        write_sample_benchmark_report(
            FIXTURE_ROOT / "agentic-login-bypass",
            output_dir,
            overwrite=True,
        )


def test_write_sample_benchmark_report_wraps_write_failures(tmp_path):
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("blocking parent", encoding="utf-8")

    with pytest.raises(BenchmarkSampleReportError, match="could not write sample report"):
        write_sample_benchmark_report(
            FIXTURE_ROOT / "agentic-login-bypass",
            parent_file / "sample-report.json",
        )


def test_write_sample_benchmark_report_wraps_temp_file_failures(tmp_path, monkeypatch):
    report_path = tmp_path / "sample-report.json"
    report_path.write_text("replace me", encoding="utf-8")

    def fail_named_temporary_file(*args, **kwargs):
        raise OSError("temp unavailable")

    monkeypatch.setattr(benchmarks.tempfile, "NamedTemporaryFile", fail_named_temporary_file)

    with pytest.raises(BenchmarkSampleReportError, match="could not write sample report"):
        write_sample_benchmark_report(
            FIXTURE_ROOT / "agentic-login-bypass",
            report_path,
            overwrite=True,
        )

    assert report_path.read_text(encoding="utf-8") == "replace me"


def test_write_sample_benchmark_report_cleans_temp_file_on_replace_failure(
    tmp_path,
    monkeypatch,
):
    report_path = tmp_path / "sample-report.json"
    report_path.write_text("replace me", encoding="utf-8")

    def fail_replace(self, target):
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(BenchmarkSampleReportError, match="could not write sample report"):
        write_sample_benchmark_report(
            FIXTURE_ROOT / "agentic-login-bypass",
            report_path,
            overwrite=True,
        )

    assert report_path.read_text(encoding="utf-8") == "replace me"
    assert list(tmp_path.glob(".sample-report.json.*.tmp")) == []


def test_write_sample_benchmark_report_rejects_symlink_output(tmp_path):
    target = tmp_path / "target-report.json"
    symlink = tmp_path / "linked-report.json"
    try:
        symlink.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(BenchmarkSampleReportError, match="must not use symlinks"):
        write_sample_benchmark_report(
            FIXTURE_ROOT / "agentic-login-bypass",
            symlink,
            overwrite=True,
        )


def test_write_sample_benchmark_report_rejects_symlink_parent(tmp_path):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    symlink_dir = tmp_path / "linked"
    try:
        symlink_dir.symlink_to(real_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(BenchmarkSampleReportError, match="must not use symlinks"):
        write_sample_benchmark_report(
            FIXTURE_ROOT / "agentic-login-bypass",
            symlink_dir / "sample-report.json",
        )


def test_write_sample_benchmark_report_uses_fixture_validation(tmp_path):
    fixture_root = _copy_fixture(tmp_path)
    expected = _load_expected(fixture_root)
    del expected["expected_findings"][0]["evidence"]
    _write_expected(fixture_root, expected)

    with pytest.raises(BenchmarkValidationError, match="evidence"):
        write_sample_benchmark_report(
            fixture_root / "agentic-login-bypass",
            tmp_path / "sample-report.json",
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda expected: expected.pop("scenario_id"), "scenario_id"),
        (lambda expected: expected.pop("expected_verdict"), "expected_verdict"),
    ],
)
def test_write_sample_benchmark_report_rejects_missing_top_level_fields(
    tmp_path,
    mutate,
    message,
):
    fixture_root = _copy_fixture(tmp_path)
    expected = _load_expected(fixture_root)
    mutate(expected)
    _write_expected(fixture_root, expected)

    with pytest.raises(BenchmarkValidationError, match=message):
        write_sample_benchmark_report(
            fixture_root / "agentic-login-bypass",
            tmp_path / "sample-report.json",
        )


def test_write_sample_benchmark_report_rejects_malformed_issue_entries(tmp_path):
    fixture_root = _copy_fixture(tmp_path)
    expected = _load_expected(fixture_root)
    expected["expected_warnings"][0] = "bad warning"
    _write_expected(fixture_root, expected)

    with pytest.raises(BenchmarkValidationError, match="must be an object"):
        write_sample_benchmark_report(
            fixture_root / "agentic-login-bypass",
            tmp_path / "sample-report.json",
        )


def test_benchmarks_sample_report_cli_writes_report(tmp_path):
    report_path = tmp_path / "sample-report.json"

    result = CliRunner().invoke(
        app,
        [
            "benchmarks",
            "sample-report",
            "--fixture",
            str(FIXTURE_ROOT / "agentic-login-bypass"),
            "--output",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert report_path.is_file()
    assert "Council Benchmark Sample Report" in result.output
    assert "score command:" in result.output
    assert "not model-run benchmark evidence" in result.output


def test_benchmarks_sample_report_cli_fails_for_existing_output(tmp_path):
    report_path = tmp_path / "sample-report.json"
    report_path.write_text("keep me", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "benchmarks",
            "sample-report",
            "--fixture",
            str(FIXTURE_ROOT / "agentic-login-bypass"),
            "--output",
            str(report_path),
        ],
    )

    assert result.exit_code == 1
    assert "Benchmark sample report failed" in result.output
    assert "already exists" in result.output


def test_benchmarks_sample_report_cli_resolves_relative_output_under_repo(tmp_path):
    repo_root = tmp_path / "repo"
    fixture_dir = repo_root / "benchmarks" / "seeded-prs" / "agentic-login-bypass"
    shutil.copytree(FIXTURE_ROOT / "agentic-login-bypass", fixture_dir)

    result = CliRunner().invoke(
        app,
        [
            "benchmarks",
            "sample-report",
            "--repo",
            str(repo_root),
            "--fixture",
            "benchmarks/seeded-prs/agentic-login-bypass",
            "--output",
            "reports/sample-report.json",
        ],
    )

    assert result.exit_code == 0
    assert (repo_root / "reports" / "sample-report.json").is_file()


def test_benchmarks_sample_report_cli_rejects_relative_output_outside_repo(tmp_path):
    repo_root = tmp_path / "repo"
    fixture_dir = repo_root / "benchmarks" / "seeded-prs" / "agentic-login-bypass"
    shutil.copytree(FIXTURE_ROOT / "agentic-login-bypass", fixture_dir)
    outside_path = tmp_path / "sample-report.json"

    result = CliRunner().invoke(
        app,
        [
            "benchmarks",
            "sample-report",
            "--repo",
            str(repo_root),
            "--fixture",
            "benchmarks/seeded-prs/agentic-login-bypass",
            "--output",
            "../sample-report.json",
        ],
    )

    assert result.exit_code == 1
    normalized_output = " ".join(result.output.split())
    assert "relative output path must stay under" in normalized_output
    assert not outside_path.exists()


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

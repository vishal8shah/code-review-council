from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from council.benchmarks import BenchmarkValidationError, validate_seeded_pr_fixtures
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

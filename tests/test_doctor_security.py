from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from council.config import load_config
from council.doctor import DoctorCheck, DoctorReport, _git_timed_out, _is_valid_branch_name, _run_git, run_doctor


def test_run_git_uses_timeout_and_hardened_env():
    completed = MagicMock(returncode=0, stdout="ok", stderr="")

    with patch("council.doctor.subprocess.run", return_value=completed) as mock_run:
        result = _run_git(Path.cwd(), "rev-parse", "HEAD")

    assert result is completed
    _, kwargs = mock_run.call_args
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["timeout"] == 10.0
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kwargs["env"]["GIT_CONFIG_NOSYSTEM"] == "1"
    assert kwargs["env"]["GIT_CONFIG_GLOBAL"] == os.devnull
    assert kwargs["env"]["GIT_CONFIG_SYSTEM"] == os.devnull
    assert kwargs["env"]["GIT_ASKPASS"] == ""
    assert kwargs["env"]["SSH_ASKPASS"] == ""
    assert kwargs["env"]["GIT_PAGER"] == "cat"


def test_run_doctor_reports_git_probe_timeout(monkeypatch):
    timeout_result = subprocess.CompletedProcess(
        args=["git", "rev-parse", "--show-toplevel"],
        returncode=124,
        stdout="",
        stderr="git command timed out after 10 seconds",
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with patch("council.doctor._run_git", return_value=timeout_result):
        report = run_doctor(repo_root=Path.cwd(), config=load_config(Path.cwd()), branch="main")

    git_repo = next(check for check in report.checks if check.name == "git_repo")
    assert git_repo.status == "FAIL"
    assert "timed out" in git_repo.detail.lower()


def test_is_valid_branch_name_accepts_valid_names():
    # git check-ref-format returns 0 for valid branches.
    ok = MagicMock(returncode=0, stdout="", stderr="")
    with patch("council.doctor._run_git", return_value=ok):
        assert _is_valid_branch_name(Path.cwd(), "main") is True
        assert _is_valid_branch_name(Path.cwd(), "feature/new-thing") is True


def test_is_valid_branch_name_rejects_empty_and_invalid():
    # Empty short-circuits without calling git.
    assert _is_valid_branch_name(Path.cwd(), "") is False

    # Non-zero returncode means check-ref-format rejected it.
    bad = MagicMock(returncode=1, stdout="", stderr="bad ref")
    with patch("council.doctor._run_git", return_value=bad):
        assert _is_valid_branch_name(Path.cwd(), "../evil") is False
        assert _is_valid_branch_name(Path.cwd(), "-flag") is False


def test_doctor_report_exit_code_reflects_fail_status():
    all_pass = DoctorReport(checks=[
        DoctorCheck(name="x", status="PASS", detail="ok"),
        DoctorCheck(name="y", status="WARN", detail="minor"),
    ])
    assert all_pass.exit_code == 0

    with_fail = DoctorReport(checks=[
        DoctorCheck(name="x", status="PASS", detail="ok"),
        DoctorCheck(name="y", status="FAIL", detail="broken"),
    ])
    assert with_fail.exit_code == 1


def test_run_git_returns_timeout_result_when_subprocess_times_out():
    with patch(
        "council.doctor.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["git", "rev-parse"], timeout=10.0),
    ):
        result = _run_git(Path.cwd(), "rev-parse", "HEAD")

    assert result.returncode == 124
    assert "timed out" in result.stderr.lower()


def test_git_timed_out_returns_true_for_timeout_result():
    result = subprocess.CompletedProcess(
        args=["git", "rev-parse"],
        returncode=124,
        stdout="",
        stderr="git command timed out after 10 seconds",
    )
    assert _git_timed_out(result) is True


def test_git_timed_out_returns_false_for_normal_failure():
    result = subprocess.CompletedProcess(
        args=["git", "rev-parse"],
        returncode=128,
        stdout="",
        stderr="fatal: not a git repository",
    )
    assert _git_timed_out(result) is False

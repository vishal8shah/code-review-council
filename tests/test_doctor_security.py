from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from council.config import load_config
from council.doctor import _run_git, run_doctor


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

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from council.diff_parser import get_current_branch, get_git_diff


def test_get_git_diff_uses_surrogateescape_decode():
    raw_stdout = b"diff --git a/a.py b/a.py\n+\xff\n"
    completed = subprocess.CompletedProcess(
        args=["git", "diff"],
        returncode=0,
        stdout=raw_stdout,
        stderr=b"",
    )

    with patch("council.diff_parser.subprocess.run", return_value=completed) as run_mock:
        diff = get_git_diff(repo_root=Path.cwd(), branch="main")

    assert diff == raw_stdout.decode("utf-8", errors="surrogateescape")
    assert diff.encode("utf-8", errors="surrogateescape") == raw_stdout
    _, kwargs = run_mock.call_args
    assert kwargs["text"] is False
    assert "encoding" not in kwargs
    assert "errors" not in kwargs


def test_get_git_diff_retries_origin_branch_with_byte_output():
    first = subprocess.CompletedProcess(
        args=["git", "diff", "--unified=3", "main...HEAD"],
        returncode=1,
        stdout=b"",
        stderr=b"fatal: unknown revision or path not in the working tree",
    )
    raw_stdout = b"fallback diff \xff"
    second = subprocess.CompletedProcess(
        args=["git", "diff", "--unified=3", "origin/main...HEAD"],
        returncode=0,
        stdout=raw_stdout,
        stderr=b"",
    )

    with patch("council.diff_parser.subprocess.run", side_effect=[first, second]) as run_mock:
        diff = get_git_diff(repo_root=Path.cwd(), branch="main")

    assert diff == raw_stdout.decode("utf-8", errors="surrogateescape")
    assert diff.encode("utf-8", errors="surrogateescape") == raw_stdout
    assert run_mock.call_count == 2
    for call in run_mock.call_args_list:
        assert call.kwargs["text"] is False


def test_get_current_branch_strips_newline_after_surrogateescape_decode():
    raw_stdout = b"feature/\xfftest\n"
    completed = subprocess.CompletedProcess(
        args=["git", "rev-parse", "--abbrev-ref", "HEAD"],
        returncode=0,
        stdout=raw_stdout,
        stderr=b"",
    )

    with patch("council.diff_parser.subprocess.run", return_value=completed) as run_mock:
        branch = get_current_branch(repo_root=Path.cwd())

    assert branch == raw_stdout.rstrip(b"\n").decode("utf-8", errors="surrogateescape")
    assert branch.encode("utf-8", errors="surrogateescape") == raw_stdout.rstrip(b"\n")
    _, kwargs = run_mock.call_args
    assert kwargs["text"] is False

from __future__ import annotations
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from council.reporters.github_pr import (
    _build_comment_body,
    _build_inline_comment_body,
    _build_inline_comment_candidates,
    _inline_key,
    _post_inline_comments,
    _resolve_github_api_url,
)
from council.schemas import ChairFinding, ChairVerdict, ReviewerOutput


def test_github_pr_comment_body_sanitizes_model_generated_content():
    verdict = ChairVerdict(
        verdict="FAIL",
        confidence=0.9,
        summary="<script>alert(1)</script> with `code` and [link]",
        rationale="r",
        accepted_blockers=[
            ChairFinding(
                severity="HIGH",
                category="security",
                file="auth.py",
                line_start=7,
                description="Use <b>unsafe</b> `markdown` [here]",
                suggestion="Replace with <safe> output",
                chair_action="accepted",
            )
        ],
    )
    reviewers = [
        ReviewerOutput(
            reviewer_id="qa",
            model="m",
            verdict="FAIL",
            confidence=0.5,
            output_mode="failed",
            error="<raw> [error] `payload`",
        )
    ]

    body = _build_comment_body(verdict, reviewers)

    assert "Model-generated summary:" in body
    assert "<script>" not in body
    assert "&lt;script&gt;" in body
    assert "`code`" not in body
    assert r"\[link\]" in body
    assert "&lt;b&gt;unsafe&lt;/b&gt;" in body
    assert "Replace with &lt;safe&gt; output" in body
    assert "<raw>" not in body


def test_inline_comment_body_sanitizes_untrusted_text():
    finding = ChairFinding(
        severity="MEDIUM",
        category="testing",
        file="tests/test_app.py",
        line_start=11,
        description="Bad <tag> with `markdown` [text]",
        suggestion="Use <plain> text",
        chair_action="accepted",
    )

    body = _build_inline_comment_body(finding, "abc123")

    assert "<tag>" not in body
    assert "&lt;tag&gt;" in body
    assert "`markdown`" not in body
    assert r"\[text\]" in body
    assert "Use &lt;plain&gt; text" in body


@pytest.mark.parametrize("raw,expected", [
    (None, "https://api.github.com"),
    ("", "https://api.github.com"),
    ("http://api.github.com", "https://api.github.com"),          # http not allowed
    ("https://api.github.com", "https://api.github.com"),
    ("https://api.github.com/", "https://api.github.com"),        # trailing slash
    ("https://ghe.example.com/api/v3", "https://ghe.example.com/api/v3"),
    ("https://ghe.example.com:8080/api/v3", "https://ghe.example.com:8080/api/v3"),
    ("https://ghe.example.com/api/v3/", "https://ghe.example.com/api/v3"),  # trailing slash
    ("https://user:pass@ghe.example.com/api/v3", "https://api.github.com"),  # credentials
    ("https://ghe.example.com/api/v3?foo=bar", "https://api.github.com"),    # query string
    ("https://ghe.example.com/api/v3#frag", "https://api.github.com"),       # fragment
    ("https://ghe.example.com/v3", "https://api.github.com"),                # wrong path
    ("https://169.254.169.254/api/v3", "https://169.254.169.254/api/v3"),    # IP allowed if /api/v3
    ("http://169.254.169.254/latest/meta-data", "https://api.github.com"),   # SSRF blocked
])
def test_resolve_github_api_url_edge_cases(raw, expected):
    assert _resolve_github_api_url(raw) == expected


def test_build_inline_comment_candidates_includes_warnings_and_respects_line_range():
    single_line = ChairFinding(
        severity="HIGH",
        category="security",
        file="app.py",
        line_start=5,
        description="single line issue",
        chair_action="accepted",
    )
    multi_line = ChairFinding(
        severity="MEDIUM",
        category="testing",
        file="app.py",
        line_start=10,
        line_end=15,
        description="multi line warning",
        chair_action="accepted",
    )
    verdict = ChairVerdict(
        verdict="FAIL",
        confidence=0.8,
        summary="s",
        rationale="r",
        accepted_blockers=[single_line],
        warnings=[multi_line],
    )

    candidates = _build_inline_comment_candidates(verdict)

    assert len(candidates) == 2
    single = next(c for c in candidates if c["path"] == "app.py" and c["line"] == 5)
    assert "start_line" not in single

    multi = next(c for c in candidates if c["line"] == 15)
    assert multi["start_line"] == 10


def test_post_inline_comments_returns_false_when_no_head_sha():
    verdict = ChairVerdict(verdict="FAIL", confidence=0.9, summary="s", rationale="r")
    result = _post_inline_comments(
        verdict=verdict,
        repo="owner/repo",
        pr_number=1,
        head_sha=None,
        headers={},
        api_url="https://api.github.com",
        timeout=5.0,
        max_retries=0,
        backoff_seconds=1.0,
    )
    assert result is False


def test_post_inline_comments_returns_false_when_no_eligible_findings():
    verdict = ChairVerdict(
        verdict="FAIL",
        confidence=0.9,
        summary="s",
        rationale="r",
        accepted_blockers=[
            ChairFinding(
                severity="HIGH",
                category="security",
                file="auth.py",
                # no line_start → not an inline candidate
                description="no line info",
                chair_action="accepted",
            )
        ],
    )
    result = _post_inline_comments(
        verdict=verdict,
        repo="owner/repo",
        pr_number=1,
        head_sha="abc123",
        headers={},
        api_url="https://api.github.com",
        timeout=5.0,
        max_retries=0,
        backoff_seconds=1.0,
    )
    assert result is False


def test_post_inline_comments_skips_duplicate_keys(monkeypatch):
    finding = ChairFinding(
        severity="HIGH",
        category="security",
        file="auth.py",
        line_start=10,
        description="issue",
        chair_action="accepted",
    )
    verdict = ChairVerdict(
        verdict="FAIL",
        confidence=0.9,
        summary="s",
        rationale="r",
        accepted_blockers=[finding],
    )

    @contextmanager
    def fake_request_with_retry(req, **kwargs):
        yield None

    with patch(
        "council.reporters.github_pr._existing_inline_keys",
        return_value={_inline_key(finding)},
    ), patch("council.reporters.github_pr._request_with_retry", fake_request_with_retry):
        result = _post_inline_comments(
            verdict=verdict,
            repo="owner/repo",
            pr_number=1,
            head_sha="abc123",
            headers={},
            api_url="https://api.github.com",
            timeout=5.0,
            max_retries=0,
            backoff_seconds=1.0,
        )

    assert result is False

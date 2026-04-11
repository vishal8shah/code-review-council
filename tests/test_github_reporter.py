from __future__ import annotations

from council.reporters.github_pr import _build_comment_body, _build_inline_comment_body
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

from __future__ import annotations

from council.chair import _build_chair_message
from council.reviewers.base import BaseReviewer
from council.schemas import Finding, ReviewerOutput, ReviewPack, SupportFileSummary


def test_reviewer_prompt_renders_support_summaries_and_guidance():
    reviewer = BaseReviewer(reviewer_id="qa", model="test")
    review_pack = ReviewPack(
        diff_text="+ pass",
        files_skipped=["tests/test_llm_transport.py"],
        support_files_outside_budget=[
            SupportFileSummary(
                path="tests/test_llm_transport.py",
                kind="test",
                status="skipped",
                related_files=["council/llm_transport.py"],
                summary="def test_extract_json_object_handles_real_triple_backtick_fences()",
            )
        ],
    )

    message = reviewer._build_user_message(review_pack)

    assert "Changed Support Files Outside Review Budget" in message
    assert "[test/skipped] tests/test_llm_transport.py -> council/llm_transport.py" in message
    assert "do not claim they are" in message
    assert "full file bodies are omitted" in message


def test_chair_prompt_renders_support_summaries_and_warning_note():
    review_pack = ReviewPack(
        diff_text="+ pass",
        changed_files=["council/llm_transport.py"],
        files_skipped=["tests/test_llm_transport.py"],
        support_files_outside_budget=[
            SupportFileSummary(
                path="tests/test_llm_transport.py",
                kind="test",
                status="skipped",
                related_files=["council/llm_transport.py"],
                summary="def test_extract_json_object_handles_real_triple_backtick_fences()",
            )
        ],
    )
    reviews = [
        ReviewerOutput(
            reviewer_id="qa",
            model="test",
            verdict="FAIL",
            confidence=0.8,
            findings=[
                Finding(
                    severity="HIGH",
                    category="testing",
                    file="council/llm_transport.py",
                    symbol_name="extract_json_object",
                    description="Claims tests are missing.",
                    suggestion="Add tests.",
                )
            ],
        )
    ]

    message = _build_chair_message(review_pack, reviews)

    assert "Changed Support Files Outside Review Budget" in message
    assert "[test/skipped] tests/test_llm_transport.py -> council/llm_transport.py" in message
    assert (
        "Support-context warning: testing/docs findings must account for summarized support files outside budget."
        in message
    )
    assert "Do not treat summarized support files outside budget as missing solely because" in message

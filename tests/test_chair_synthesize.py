from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from council.chair import synthesize
from council.llm_transport import JSONCompletionResult
from council.schemas import Finding, ReviewerOutput, ReviewPack


@pytest.mark.asyncio
async def test_synthesize_fast_path_passes_without_llm_call():
    review_pack = ReviewPack(diff_text="+x")
    reviews = [ReviewerOutput(reviewer_id="qa", model="m", verdict="PASS", confidence=0.9, findings=[])]

    verdict = await synthesize(review_pack, reviews)

    assert verdict.verdict == "PASS"
    assert verdict.summary == "All reviewers passed with no findings."


@pytest.mark.asyncio
async def test_synthesize_invalid_json_fails_closed():
    review_pack = ReviewPack(diff_text="+x")
    reviews = [
        ReviewerOutput(
            reviewer_id="secops",
            model="m",
            verdict="FAIL",
            confidence=0.9,
            findings=[
                Finding(
                    severity="HIGH",
                    category="security",
                    file="auth.py",
                    description="Issue",
                    suggestion="Fix",
                )
            ],
        )
    ]

    with patch(
        "council.chair.invoke_json_completion",
        new=AsyncMock(
            return_value=JSONCompletionResult(
                raw_content="not valid json",
                tokens_used=3,
                output_mode="response_format",
            )
        ),
    ):
        verdict = await synthesize(review_pack, reviews)

    assert verdict.verdict == "FAIL"
    assert "Invalid JSON returned by chair model" in verdict.summary

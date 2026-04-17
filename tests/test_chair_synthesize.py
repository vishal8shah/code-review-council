from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from council.chair import _chair_failure_verdict, _parse_chair_findings, synthesize
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
    assert verdict.summary == "Chair synthesis failed; review failed closed for safety."
    assert verdict.rationale == (
        "Chair synthesis transport or parsing failed. The review failed closed for safety."
    )
    assert verdict.degraded_reasons == [
        "Chair synthesis failed due to an internal transport or parsing error."
    ]


def test_parse_chair_findings_logs_malformed_items(caplog):
    raw = [
        {
            "severity": "HIGH",
            "category": "security",
            "file": "auth.py",
            "description": "Real one",
            "chair_action": "accepted",
        },
        {"not": "a valid finding"},  # missing required fields
        "totally malformed string",
    ]

    with caplog.at_level("DEBUG", logger="council.chair"):
        findings = _parse_chair_findings(raw)

    # Only the well-formed one survives.
    assert len(findings) == 1
    assert findings[0].description == "Real one"
    # Malformed items are surfaced in logs at WARNING, not silently dropped.
    log_text = " ".join(record.message for record in caplog.records)
    assert "malformed chair finding" in log_text.lower()
    warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("2" in r.message and "malformed" in r.message.lower() for r in warning_records)


def test_chair_failure_verdict_does_not_leak_exception_text():
    verdict = _chair_failure_verdict(
        RuntimeError("secret token 123"),
        degraded_reasons=["existing"],
    )

    assert verdict.summary == "Chair synthesis failed; review failed closed for safety."
    assert "secret token 123" not in verdict.summary
    assert "secret token 123" not in verdict.rationale
    assert all("secret token 123" not in reason for reason in verdict.degraded_reasons)

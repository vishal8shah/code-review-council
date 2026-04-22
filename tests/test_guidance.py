from __future__ import annotations

import pytest

from council.guidance import (
    build_engineer_review_note,
    build_fix_prompt,
    build_review_next_steps,
    build_verification_step,
    build_why_it_matters,
)
from council.schemas import ChairFinding, ChairVerdict


def _finding(**overrides) -> ChairFinding:
    values = {
        "severity": "HIGH",
        "category": "security",
        "file": "src/auth.py",
        "line_start": 12,
        "line_end": 14,
        "symbol_name": "validate_token",
        "description": "Token validation accepts expired tokens",
        "suggestion": "Reject tokens after their expiry timestamp",
        "evidence_ref": "diff hunk @ src/auth.py:12",
        "chair_action": "accepted",
    }
    values.update(overrides)
    return ChairFinding(**values)


def test_fix_prompt_is_specific_and_copyable():
    prompt = build_fix_prompt(_finding())

    assert "src/auth.py:12-14" in prompt
    assert "`validate_token`" in prompt
    assert "high security issue" in prompt
    assert "Reject tokens after their expiry timestamp" in prompt
    assert "diff hunk @ src/auth.py:12" in prompt
    assert "add or update tests" in prompt


@pytest.mark.parametrize(
    "category,expected",
    [
        ("security", "security"),
        ("testing", "test suite"),
        ("architecture", "affected area"),
        ("documentation", "updated docs"),
        ("performance", "benchmark"),
        ("style", "formatter"),
    ],
)
def test_verification_step_is_category_specific(category: str, expected: str):
    assert expected in build_verification_step(_finding(category=category)).lower()


def test_engineer_review_note_escalates_high_impact_and_sensitive_changes():
    assert build_engineer_review_note(_finding(severity="HIGH")) is not None
    assert build_engineer_review_note(
        _finding(
            severity="LOW",
            category="style",
            file="config/settings.py",
            description="Rename token helper for clarity",
        )
    ) is not None
    assert build_engineer_review_note(
        _finding(
            severity="LOW",
            category="style",
            file="docs/usage.md",
            description="Sentence could be clearer",
            suggestion="Rewrite the sentence",
            symbol_name=None,
        )
    ) is None


def test_why_it_matters_has_plain_english_fallback():
    assert "user data" in build_why_it_matters(_finding(category="security"))


def test_review_next_steps_cover_pass_and_degraded_failures():
    pass_verdict = ChairVerdict(
        verdict="PASS",
        confidence=0.95,
        summary="Clean.",
        rationale="No accepted findings.",
    )
    fail_verdict = ChairVerdict(
        verdict="FAIL",
        confidence=0.75,
        degraded=True,
        degraded_reasons=["qa: timeout"],
        summary="One blocker found.",
        accepted_blockers=[_finding()],
    )

    assert build_review_next_steps(pass_verdict) == [
        "No blocking action is required; keep the report as review evidence."
    ]
    fail_steps = build_review_next_steps(fail_verdict)
    assert any("degraded review integrity" in step for step in fail_steps)
    assert any("accepted blocker" in step for step in fail_steps)
    assert fail_steps[-1].startswith("Re-run the same `council review` command")

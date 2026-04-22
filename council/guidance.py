"""Deterministic next-step guidance for Council findings and verdicts."""

from __future__ import annotations

from .schemas import ChairFinding, ChairVerdict


_WHY_IT_MATTERS = {
    "security": "This could expose user data, account access, or other sensitive behavior to attackers.",
    "testing": "Without tests, a broken change can slip through undetected and reach production.",
    "architecture": "This could make the codebase brittle, harder to maintain, or more likely to fail under real usage.",
    "documentation": "Missing or inaccurate documentation slows future work and increases the chance of misuse.",
    "performance": "This could cause slower responses or higher infrastructure costs at scale.",
    "style": "Inconsistent style makes the code harder to read and maintain over time.",
}

_VERIFY_AFTER_FIX = {
    "security": "Re-run the affected security, auth, or data flow and add a regression test proving the issue is no longer reproducible.",
    "testing": "Run the targeted test file plus the broader test suite and confirm the new coverage fails before the fix and passes after it.",
    "architecture": "Run the existing tests for the affected area and manually exercise the changed code path for edge cases.",
    "documentation": "Preview or read the updated docs and confirm they match the shipped behavior and commands.",
    "performance": "Run the relevant benchmark, profile, or high-volume path and compare the result against the current behavior.",
    "style": "Run the project's formatter or linter and confirm the style warning is gone without changing behavior.",
}

_ENGINEER_REVIEW_KEYWORDS = frozenset(
    {
        "auth",
        "authorization",
        "credential",
        "delete",
        "infra",
        "permission",
        "secret",
        "token",
    }
)


def _location(finding: ChairFinding) -> str:
    location = finding.file
    if finding.line_start:
        location += f":{finding.line_start}"
        if finding.line_end and finding.line_end != finding.line_start:
            location += f"-{finding.line_end}"
    return location


def build_fix_prompt(finding: ChairFinding) -> str:
    """Return a copy/paste prompt for a coding assistant."""
    symbol = f" in `{finding.symbol_name}`" if finding.symbol_name else ""
    evidence = f" Evidence to preserve: {finding.evidence_ref}." if finding.evidence_ref else ""
    suggestion = f" Recommended direction: {finding.suggestion}." if finding.suggestion else ""
    return (
        f"In {_location(finding)}{symbol}, fix this {finding.severity.lower()} "
        f"{finding.category} issue: {finding.description}.{suggestion}{evidence} "
        "Preserve existing behavior, keep the patch focused, and add or update tests that prove the fix."
    )


def build_verification_step(finding: ChairFinding) -> str:
    """Return deterministic verification guidance for a fixed finding."""
    return _VERIFY_AFTER_FIX.get(
        finding.category,
        "Re-run the affected flow and confirm the issue no longer occurs.",
    )


def build_engineer_review_note(finding: ChairFinding) -> str | None:
    """Return a human-review escalation note when a fix deserves extra care."""
    haystack = " ".join(
        part
        for part in (
            finding.file,
            finding.category,
            finding.description,
            finding.suggestion,
            finding.symbol_name or "",
        )
        if part
    ).lower()
    if finding.severity in {"CRITICAL", "HIGH"} or finding.category in {"security", "architecture"}:
        return "Have a developer review the patch before merging because this finding is high impact."
    if any(keyword in haystack for keyword in _ENGINEER_REVIEW_KEYWORDS):
        return "Have a developer review the patch before merging because this touches sensitive behavior."
    return None


def build_why_it_matters(finding: ChairFinding) -> str:
    """Return a plain-English impact statement for owner fallbacks."""
    return _WHY_IT_MATTERS.get(
        finding.category,
        "This could create product risk if merged without review.",
    )


def build_review_next_steps(verdict: ChairVerdict) -> list[str]:
    """Return concise next steps for terminal and PR summaries."""
    steps: list[str] = []
    if verdict.degraded:
        steps.append("Resolve the degraded review integrity issue, then re-run Council before merging.")
    if verdict.accepted_blockers:
        steps.append("Fix each accepted blocker and add or update tests that prove the fix.")
    if verdict.warnings:
        steps.append("Review accepted warnings and either address them now or track them explicitly.")
    if verdict.dismissed_findings:
        steps.append("Skim dismissed findings for context, but do not treat them as merge blockers.")
    if verdict.verdict == "PASS" and not verdict.degraded:
        steps.append("No blocking action is required; keep the report as review evidence.")
    else:
        steps.append("Re-run the same `council review` command locally or wait for CI to re-run on the next push.")
    return steps

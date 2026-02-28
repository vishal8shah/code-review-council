"""Council Chair — synthesizes reviewer outputs into a final verdict.

The Chair receives all reviewer findings and makes evidence-based
adjudication decisions. Each finding is explicitly accepted or dismissed.
"""

from __future__ import annotations

import json

import litellm

from .schemas import ChairFinding, ChairVerdict, ReviewerOutput, ReviewPack


CHAIR_SYSTEM_PROMPT = """You are the Council Chair of a Code Review Council. You receive independent
reviews from multiple specialized reviewers and must synthesize them into a
single, authoritative verdict.

## Your Responsibilities
1. Evaluate each finding individually — accept or dismiss based on its evidence
2. Require evidence — a finding without specific code reference should be dismissed
3. Adjudicate conflicts — when reviewers disagree, reason about which is correct
4. Classify decisions — mark each finding as accepted/dismissed/downgraded/upgraded
5. Render verdict — PASS, PASS_WITH_WARNINGS, or FAIL

## Verdict Logic (Evidence-Based)
- FAIL: Any accepted finding with severity CRITICAL that cites specific code evidence
- PASS_WITH_WARNINGS: Accepted HIGH or MEDIUM findings that are real but not blocking
- PASS: No accepted findings above LOW

## Hard Overrides
- SecOps CRITICAL findings with evidence are always accepted as blockers
- Findings without evidence_ref or symbol_name should be dismissed or downgraded
- If a reviewer has error set (failed/timed out), reduce confidence in the verdict
- If a reviewer finding reinforces a Gate Zero static analysis finding, it carries more weight

## Conflict Resolution
- 2+ reviewers flag the same symbol/line → strong signal, upgrade confidence
- Single reviewer with high confidence + clear evidence → accept on merit
- Single reviewer with low confidence or vague evidence → dismiss or downgrade

Respond with ONLY a valid JSON object. Here is the exact schema:
{
  "verdict": "PASS",
  "confidence": 0.85,
  "degraded": false,
  "summary": "2-3 sentence executive summary of the review",
  "accepted_blockers": [
    {
      "severity": "CRITICAL",
      "category": "security",
      "file": "path/to/file.py",
      "line_start": 42,
      "line_end": 55,
      "symbol_name": "function_name",
      "description": "Clear description of the blocking issue",
      "suggestion": "Specific fix recommendation",
      "evidence_ref": "The code evidence that demonstrates the issue",
      "policy_id": null,
      "confidence": 0.9,
      "source_reviewers": ["secops"],
      "consensus": false,
      "chair_action": "accepted",
      "chair_reasoning": "Why this finding was accepted as a blocker"
    }
  ],
  "warnings": [
    {
      "severity": "MEDIUM",
      "category": "architecture",
      "file": "path/to/file.py",
      "line_start": 78,
      "line_end": 90,
      "symbol_name": null,
      "description": "Non-blocking issue worth noting",
      "suggestion": "Recommended improvement",
      "evidence_ref": "Supporting evidence",
      "policy_id": null,
      "confidence": 0.7,
      "source_reviewers": ["architect"],
      "consensus": false,
      "chair_action": "accepted",
      "chair_reasoning": "Accepted as warning, not blocking"
    }
  ],
  "dismissed_findings": [
    {
      "severity": "HIGH",
      "category": "style",
      "file": "path/to/file.py",
      "line_start": null,
      "line_end": null,
      "symbol_name": null,
      "description": "Original finding that was dismissed",
      "suggestion": "",
      "evidence_ref": null,
      "policy_id": null,
      "confidence": 0.3,
      "source_reviewers": ["docs"],
      "consensus": false,
      "chair_action": "dismissed",
      "chair_reasoning": "No evidence provided; stylistic preference without policy backing"
    }
  ],
  "all_findings": [],
  "reviewer_agreement_score": 0.75,
  "rationale": "Detailed reasoning for the verdict including how conflicts were resolved"
}"""


def _build_chair_message(review_pack: ReviewPack, reviews: list[ReviewerOutput]) -> str:
    """Build the user message for the Chair containing all reviewer outputs."""
    # ReviewPack summary
    symbols_text = ""
    if review_pack.changed_symbols:
        symbols_text = "\n### Changed Symbols\n"
        for sym in review_pack.changed_symbols:
            test_info = "has tests" if sym.has_tests else "NO tests"
            symbols_text += (
                f"- {sym.kind} `{sym.name}` in {sym.file}:{sym.line_start}-{sym.line_end} "
                f"({sym.change_type}, {test_info})\n"
            )

    gate_zero_text = ""
    if review_pack.gate_zero_results:
        gate_zero_text = "\n### Gate Zero Static Analysis Findings\n"
        for g in review_pack.gate_zero_results:
            loc = f"{g.file}:{g.line_start}" if g.line_start else g.file
            gate_zero_text += f"- [{g.severity}] {g.check}: {loc} — {g.message}\n"

    skipped_text = ""
    if review_pack.files_skipped:
        skipped_text = f"\n### Files Skipped by Preprocessor\n{', '.join(review_pack.files_skipped)}\n"
    if review_pack.files_truncated:
        skipped_text += f"\n### Files Truncated\n{', '.join(review_pack.files_truncated)}\n"

    policies_text = ""
    if review_pack.repo_policies:
        policies_text = "\n### Active Repo Policies\n"
        for key, val in review_pack.repo_policies.items():
            policies_text += f"- {key}: {val}\n"

    # Serialize reviewer outputs
    reviews_data = []
    for r in reviews:
        reviews_data.append({
            "reviewer_id": r.reviewer_id,
            "model": r.model,
            "verdict": r.verdict,
            "confidence": r.confidence,
            "error": r.error,
            "reasoning": r.reasoning,
            "findings": [f.model_dump() for f in r.findings],
        })

    return f"""# Council Chair Review

## ReviewPack Summary
- Files changed: {len(review_pack.changed_files)}
- Lines changed: {review_pack.total_lines_changed}
- Languages: {', '.join(review_pack.languages_detected)}
- Files skipped by preprocessor: {len(review_pack.files_skipped)}
- Files truncated: {len(review_pack.files_truncated)}
{symbols_text}{gate_zero_text}{skipped_text}{policies_text}
## Reviewer Outputs
```json
{json.dumps(reviews_data, indent=2)}
```

Evaluate each finding individually. Accept or dismiss with explicit reasoning.
If a reviewer finding reinforces a Gate Zero finding, it carries more weight.
Render your final verdict as JSON."""


async def synthesize(
    review_pack: ReviewPack,
    reviews: list[ReviewerOutput],
    chair_model: str = "openai/gpt-4o",
    degraded: bool = False,
    degraded_reasons: list[str] | None = None,
    timeout: float = 120.0,
) -> ChairVerdict:
    """Run the Chair synthesis to produce a final verdict.

    Args:
        review_pack: The ReviewPack that was sent to all reviewers.
        reviews: Outputs from all reviewers (including failed ones).
        chair_model: LiteLLM model identifier for the Chair.
        degraded: Whether any reviewer failed/timed out.
        timeout: LLM call timeout.

    Returns:
        ChairVerdict with accepted/dismissed findings and verdict.
    """
    # If all reviewers passed with no findings, fast-path to PASS
    all_findings = [f for r in reviews for f in r.findings]
    all_errored = all(r.error is not None for r in reviews)

    if not all_findings and not all_errored:
        return ChairVerdict(
            verdict="PASS",
            confidence=0.95 if not degraded else 0.7,
            degraded=degraded,
            degraded_reasons=degraded_reasons or [],
            summary="All reviewers passed with no findings.",
            accepted_blockers=[],
            dismissed_findings=[],
            all_findings=[],
            reviewer_agreement_score=1.0,
            rationale="No findings from any reviewer. Code passes review.",
        )

    try:
        response = await litellm.acompletion(
            model=chair_model,
            messages=[
                {"role": "system", "content": CHAIR_SYSTEM_PROMPT},
                {"role": "user", "content": _build_chair_message(review_pack, reviews)},
            ],
            response_format={"type": "json_object"},
            timeout=timeout,
            temperature=0.1,
            num_retries=2,
        )

        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)

        # Parse accepted blockers
        accepted = []
        for f in parsed.get("accepted_blockers", []):
            try:
                accepted.append(ChairFinding(**f))
            except Exception:
                continue

        # Parse warnings (non-blocking accepted findings)
        warnings = []
        for f in parsed.get("warnings", []):
            try:
                warnings.append(ChairFinding(**f))
            except Exception:
                continue

        # Parse dismissed findings
        dismissed = []
        for f in parsed.get("dismissed_findings", []):
            try:
                dismissed.append(ChairFinding(**f))
            except Exception:
                continue

        # Parse all findings
        all_chair_findings = []
        for f in parsed.get("all_findings", []):
            try:
                all_chair_findings.append(ChairFinding(**f))
            except Exception:
                continue

        return ChairVerdict(
            verdict=parsed.get("verdict", "PASS"),
            confidence=parsed.get("confidence", 0.5),
            degraded=degraded or parsed.get("degraded", False),
            degraded_reasons=degraded_reasons or [],
            summary=parsed.get("summary", ""),
            accepted_blockers=accepted,
            warnings=warnings,
            dismissed_findings=dismissed,
            all_findings=all_chair_findings,
            reviewer_agreement_score=parsed.get("reviewer_agreement_score", 0.5),
            rationale=parsed.get("rationale", ""),
        )

    except Exception as e:
        # Chair failure is serious — fail closed in CI, fail open in advisory
        return ChairVerdict(
            verdict="FAIL",
            confidence=0.0,
            degraded=True,
            degraded_reasons=(degraded_reasons or []) + [f"Chair synthesis failed: {e}"],
            summary=f"Chair synthesis failed: {e}",
            accepted_blockers=[],
            dismissed_findings=[],
            all_findings=[],
            reviewer_agreement_score=0.0,
            rationale=f"Chair LLM call failed. Failing closed for safety. Error: {e}",
        )

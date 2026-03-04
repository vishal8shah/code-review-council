"""JSON reporter — machine-readable output for CI integration."""

from __future__ import annotations

import json
from pathlib import Path

from ..schemas import ChairVerdict, ReviewerOutput, ReviewPack


def write_json_report(
    verdict: ChairVerdict,
    output_path: str | Path,
    review_pack: ReviewPack | None = None,
    reviewer_outputs: list[ReviewerOutput] | None = None,
) -> None:
    """Write the verdict and findings as a JSON file."""
    report = {
        "verdict": verdict.verdict,
        "confidence": verdict.confidence,
        "degraded": verdict.degraded,
        "degraded_reasons": verdict.degraded_reasons,
        "summary": verdict.summary,
        "rationale": verdict.rationale,
        "reviewer_agreement_score": verdict.reviewer_agreement_score,
        "accepted_blockers": [f.model_dump() for f in verdict.accepted_blockers],
        "warnings": [f.model_dump() for f in verdict.warnings],
        "dismissed_findings": [f.model_dump() for f in verdict.dismissed_findings],
    }

    if review_pack:
        report["metadata"] = {
            "files_changed": len(review_pack.changed_files),
            "lines_changed": review_pack.total_lines_changed,
            "languages": review_pack.languages_detected,
            "files_skipped": review_pack.files_skipped,
            "token_estimate": review_pack.token_estimate,
        }

    if reviewer_outputs:
        report["reviewers"] = [
            {
                "reviewer_id": r.reviewer_id,
                "model": r.model,
                "verdict": r.verdict,
                "findings_count": len(r.findings),
                "confidence": r.confidence,
                "error": r.error,
                "integrity_error": r.integrity_error,
                "tokens_used": r.tokens_used,
            }
            for r in reviewer_outputs
        ]

    path = Path(output_path)
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

"""Markdown reporter - writes .council-review.md."""

from __future__ import annotations

from pathlib import Path

from ..schemas import ChairFinding, ChairVerdict, OwnerFindingView, ReviewerOutput, ReviewPack

VERDICT_ICONS = {"PASS": "[PASS]", "PASS_WITH_WARNINGS": "[WARN]", "FAIL": "[FAIL]"}

_URGENCY_ICONS = {
    "fix_before_merge": "[BLOCKER]",
    "fix_soon": "[SOON]",
    "nice_to_have": "[IDEA]",
}

_MERGE_REC_LABELS = {
    "SAFE_TO_MERGE": "SAFE TO MERGE",
    "MERGE_WITH_CAUTION": "MERGE WITH CAUTION",
    "FIX_BEFORE_MERGE": "FIX BEFORE MERGE",
}


def write_markdown_report(
    verdict: ChairVerdict,
    output_path: str | Path = ".council-review.md",
    review_pack: ReviewPack | None = None,
    reviewer_outputs: list[ReviewerOutput] | None = None,
    audience: str = "developer",
) -> None:
    """Write the council review as a markdown file."""
    if audience == "owner" and verdict.owner_presentation is not None:
        _write_owner_markdown(verdict, output_path, review_pack, reviewer_outputs)
    else:
        _write_developer_markdown(verdict, output_path, review_pack, reviewer_outputs)


def _write_owner_markdown(
    verdict: ChairVerdict,
    output_path: str | Path,
    review_pack: ReviewPack | None,
    reviewer_outputs: list[ReviewerOutput] | None,
) -> None:
    """Write an owner-audience markdown report."""
    op = verdict.owner_presentation
    assert op is not None

    icon = VERDICT_ICONS.get(verdict.verdict, "?")
    lines: list[str] = []

    lines.append(f"# Code Review Council - {icon} {verdict.verdict} (Owner Report)")
    lines.append("")
    lines.append(f"## {_MERGE_REC_LABELS.get(op.merge_recommendation, op.merge_recommendation)}")
    lines.append("")
    lines.append(f"**Risk**: {op.risk_level.upper()} | {op.confidence_label}")
    lines.append("")
    lines.append(op.short_summary)
    lines.append("")

    if op.degraded_warning:
        lines.append(f"> [WARN] **Note**: {op.degraded_warning}")
        lines.append("")

    if op.findings:
        lines.append("## Issues")
        lines.append("")
        for finding in op.findings:
            _write_owner_finding(lines, finding)
    elif op.merge_recommendation == "SAFE_TO_MERGE" and not (
        verdict.accepted_blockers or verdict.warnings
    ):
        lines.append("## Issues")
        lines.append("")
        lines.append("No issues require your attention.")
        lines.append("")
    else:
        lines.append("## Issues")
        lines.append("")
        lines.append(
            "> [WARN] Detailed owner issue cards could not be generated for this report. "
            "Please review the technical appendix below for the full list of accepted findings."
        )
        lines.append("")

    has_tech = bool(verdict.accepted_blockers or verdict.warnings or verdict.dismissed_findings)
    if has_tech or verdict.rationale or reviewer_outputs or review_pack:
        lines.append("---")
        lines.append("")
        lines.append("## Technical Appendix")
        lines.append("")
        lines.append(
            "> The following sections are for developer reference. "
            "The review engine is identical for both audiences."
        )
        lines.append("")

        if review_pack:
            lines.append("### Review Metadata")
            lines.append(f"- **Files changed**: {len(review_pack.changed_files)}")
            lines.append(f"- **Lines changed**: {review_pack.total_lines_changed}")
            lines.append(f"- **Languages**: {', '.join(review_pack.languages_detected)}")
            if review_pack.files_skipped:
                lines.append(f"- **Skipped**: {', '.join(review_pack.files_skipped[:5])}")
            lines.append("")

        if reviewer_outputs:
            lines.append("### Reviewer Panel")
            lines.append("| Reviewer | Model | Verdict | Findings | Error |")
            lines.append("|----------|-------|---------|----------|-------|")
            for reviewer in reviewer_outputs:
                err = reviewer.error[:40] if reviewer.error else ""
                lines.append(
                    f"| {reviewer.reviewer_id} | {reviewer.model} | {reviewer.verdict} | "
                    f"{len(reviewer.findings)} | {err} |"
                )
            lines.append("")

        if verdict.accepted_blockers:
            lines.append("### Accepted Blockers")
            for finding in verdict.accepted_blockers:
                _write_finding(lines, finding)

        if verdict.warnings:
            lines.append("### Warnings (Non-Blocking)")
            for finding in verdict.warnings:
                _write_finding(lines, finding)

        if verdict.dismissed_findings:
            lines.append("### Dismissed Findings")
            for finding in verdict.dismissed_findings:
                _write_finding(lines, finding)

        if verdict.rationale:
            lines.append("### Chair Rationale")
            lines.append(verdict.rationale)
            lines.append("")

    lines.append("")
    lines.append(
        "*Generated by Code Review Council - owner audience - "
        "same underlying findings as the developer report.*"
    )

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def _write_owner_finding(lines: list[str], finding: OwnerFindingView) -> None:
    """Append an owner-audience finding card to markdown output."""
    icon = _URGENCY_ICONS.get(finding.urgency, "[INFO]")
    urgency_label = finding.urgency.replace("_", " ").title()
    lines.append(f"### {icon} {finding.title}")
    lines.append(f"**{finding.severity_label}** - {urgency_label}")
    lines.append("")
    lines.append(f"**What is wrong**: {finding.plain_explanation}")
    lines.append("")
    lines.append(f"**Why it matters**: {finding.why_it_matters}")
    lines.append("")
    lines.append("**Fix prompt**:")
    lines.append("```")
    lines.append(finding.fix_prompt)
    lines.append("```")
    lines.append("")
    lines.append(f"**After fixing**: {finding.test_after_fix}")
    if finding.involve_engineer:
        lines.append("")
        lines.append(f"> [ENGINEER] **Engineer needed**: {finding.involve_engineer}")
    lines.append("")


def _write_developer_markdown(
    verdict: ChairVerdict,
    output_path: str | Path,
    review_pack: ReviewPack | None,
    reviewer_outputs: list[ReviewerOutput] | None,
) -> None:
    """Write the standard developer-audience markdown report."""
    icon = VERDICT_ICONS.get(verdict.verdict, "?")
    lines: list[str] = []

    lines.append(f"# Code Review Council - {icon} {verdict.verdict}")
    lines.append("")

    if verdict.degraded:
        lines.append("> [WARN] **Degraded run**: integrity issues detected.")
        for reason in verdict.degraded_reasons:
            lines.append(f"> - {reason}")
        lines.append("")

    if verdict.summary:
        lines.append(f"**Summary**: {verdict.summary}")
        lines.append("")

    if review_pack:
        lines.append("## Review Metadata")
        lines.append(f"- **Files changed**: {len(review_pack.changed_files)}")
        lines.append(f"- **Lines changed**: {review_pack.total_lines_changed}")
        lines.append(f"- **Languages**: {', '.join(review_pack.languages_detected)}")
        lines.append(f"- **Token estimate**: {review_pack.token_estimate}")
        if review_pack.files_skipped:
            lines.append(f"- **Skipped**: {', '.join(review_pack.files_skipped[:5])}")
        lines.append("")

    if reviewer_outputs:
        lines.append("## Reviewer Panel")
        lines.append("| Reviewer | Model | Verdict | Findings | Error |")
        lines.append("|----------|-------|---------|----------|-------|")
        for reviewer in reviewer_outputs:
            err = reviewer.error[:40] if reviewer.error else ""
            lines.append(
                f"| {reviewer.reviewer_id} | {reviewer.model} | {reviewer.verdict} | "
                f"{len(reviewer.findings)} | {err} |"
            )
        lines.append("")

    if verdict.accepted_blockers:
        lines.append("## Accepted Findings (Blockers)")
        for finding in verdict.accepted_blockers:
            _write_finding(lines, finding)

    if verdict.warnings:
        lines.append("## Warnings (Non-Blocking)")
        for finding in verdict.warnings:
            _write_finding(lines, finding)

    if verdict.dismissed_findings:
        lines.append("## Dismissed Findings")
        for finding in verdict.dismissed_findings:
            _write_finding(lines, finding)

    if verdict.rationale:
        lines.append("## Chair Rationale")
        lines.append(verdict.rationale)
        lines.append("")

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def _write_finding(lines: list[str], finding: ChairFinding) -> None:
    """Append a technical finding to the markdown output."""
    location = finding.file
    if finding.line_start:
        location += f":{finding.line_start}"
    symbol = f" `{finding.symbol_name}`" if finding.symbol_name else ""
    lines.append(f"\n### {finding.severity} [{finding.category}] {location}{symbol}")
    lines.append(f"{finding.description}")
    if finding.evidence_ref:
        lines.append(f"\n> Evidence: {finding.evidence_ref}")
    if finding.suggestion:
        lines.append(f"\n**Fix**: {finding.suggestion}")
    if finding.chair_reasoning:
        lines.append(f"\n*Chair*: {finding.chair_reasoning}")
    lines.append("")

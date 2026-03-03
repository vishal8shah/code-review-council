"""Markdown reporter — writes .council-review.md.

Supports two audience modes:
  - developer (default): full technical detail with all findings
  - owner: executive summary with trust signal, top risks, reviewer health
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from ..chair import owner_summary
from ..schemas import ChairFinding, ChairVerdict, ReviewerOutput, ReviewPack

VERDICT_ICONS = {"PASS": "\u2705", "PASS_WITH_WARNINGS": "\u26a0\ufe0f", "FAIL": "\u274c"}

_TRUST_ICONS = {
    "trusted": "\u2705",
    "caution": "\u26a0\ufe0f",
    "untrusted": "\u274c",
}


def write_markdown_report(
    verdict: ChairVerdict,
    output_path: str | Path = ".council-review.md",
    review_pack: ReviewPack | None = None,
    reviewer_outputs: list[ReviewerOutput] | None = None,
    audience: Literal["developer", "owner"] = "developer",
) -> None:
    """Write the council review as a markdown file."""
    if audience == "owner":
        content = _render_owner_markdown(verdict, review_pack, reviewer_outputs)
    else:
        content = _render_developer_markdown(verdict, review_pack, reviewer_outputs)
    Path(output_path).write_text(content, encoding="utf-8")


def _render_owner_markdown(
    verdict: ChairVerdict,
    review_pack: ReviewPack | None = None,
    reviewer_outputs: list[ReviewerOutput] | None = None,
) -> str:
    """Render an owner-audience markdown report with trust signal."""
    summary = owner_summary(verdict, reviewer_outputs)
    trust_icon = _TRUST_ICONS.get(summary["trust_signal"], "?")
    lines: list[str] = []

    lines.append(f"# {trust_icon} Code Review Council \u2014 {summary['label']}")
    lines.append("")
    lines.append(f"> {summary['headline']}")
    lines.append("")
    lines.append(f"**Trust**: {summary['trust_signal']} | **Confidence**: {summary['confidence']:.0%}")
    lines.append("")

    if verdict.degraded:
        lines.append("> \u26a0\ufe0f **Degraded run**: integrity issues detected.")
        for reason in verdict.degraded_reasons:
            lines.append(f"> - {reason}")
        lines.append("")

    if review_pack:
        lines.append("## Overview")
        lines.append(f"- **Files changed**: {len(review_pack.changed_files)}")
        lines.append(f"- **Lines changed**: {review_pack.total_lines_changed}")
        lines.append(f"- **Languages**: {', '.join(review_pack.languages_detected)}")
        lines.append("")

    if summary["top_risks"]:
        lines.append("## Top Risks")
        for i, risk in enumerate(summary["top_risks"], 1):
            lines.append(f"{i}. {risk}")
        lines.append("")

    if summary["reviewer_health"]:
        lines.append("## Reviewer Health")
        lines.append("| Reviewer | Status |")
        lines.append("|----------|--------|")
        for rh in summary["reviewer_health"]:
            status_icon = "\u2705" if rh["status"] == "ok" else "\u26a0\ufe0f"
            lines.append(f"| {rh['id']} | {status_icon} {rh['status']} |")
        lines.append("")

    if verdict.rationale:
        lines.append("## Rationale")
        lines.append(verdict.rationale)
        lines.append("")

    # Empty-state trust fix: if no risks and no degradation, show explicit trust line
    if not summary["top_risks"] and not verdict.degraded:
        lines.append("---")
        lines.append(f"\u2705 **All reviewers passed.** This change is trusted at {summary['confidence']:.0%} confidence.")
        lines.append("")

    return "\n".join(lines)


def _render_developer_markdown(
    verdict: ChairVerdict,
    review_pack: ReviewPack | None = None,
    reviewer_outputs: list[ReviewerOutput] | None = None,
) -> str:
    """Render the full technical markdown report (existing behavior)."""
    icon = VERDICT_ICONS.get(verdict.verdict, "?")
    lines: list[str] = []

    lines.append(f"# Code Review Council \u2014 {icon} {verdict.verdict}")
    lines.append("")

    if verdict.degraded:
        lines.append("> \u26a0\ufe0f **Degraded run**: integrity issues detected.")
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
        for r in reviewer_outputs:
            err = r.error[:40] if r.error else ""
            lines.append(
                f"| {r.reviewer_id} | {r.model} | {r.verdict} | {len(r.findings)} | {err} |"
            )
        lines.append("")

    if verdict.accepted_blockers:
        lines.append("## Accepted Findings (Blockers)")
        for f in verdict.accepted_blockers:
            _write_finding(lines, f)

    if verdict.warnings:
        lines.append("## Warnings (Non-Blocking)")
        for f in verdict.warnings:
            _write_finding(lines, f)

    if verdict.dismissed_findings:
        lines.append("## Dismissed Findings")
        for f in verdict.dismissed_findings:
            _write_finding(lines, f)

    if verdict.rationale:
        lines.append("## Chair Rationale")
        lines.append(verdict.rationale)
        lines.append("")

    # Empty-state trust fix: when developer markdown has no findings, make it explicit
    if not verdict.accepted_blockers and not verdict.warnings and not verdict.dismissed_findings:
        if not verdict.degraded:
            lines.append("---")
            lines.append("\u2705 **Clean review.** No findings from any reviewer.")
            lines.append("")

    return "\n".join(lines)


def _write_finding(lines: list[str], f: ChairFinding) -> None:
    """Append a finding to the markdown output."""
    loc = f.file
    if f.line_start:
        loc += f":{f.line_start}"
    sym = f" `{f.symbol_name}`" if f.symbol_name else ""
    lines.append(f"\n### {f.severity} [{f.category}] {loc}{sym}")
    lines.append(f"{f.description}")
    if f.evidence_ref:
        lines.append(f"\n> Evidence: {f.evidence_ref}")
    if f.suggestion:
        lines.append(f"\n**Fix**: {f.suggestion}")
    if f.chair_reasoning:
        lines.append(f"\n*Chair*: {f.chair_reasoning}")
    lines.append("")

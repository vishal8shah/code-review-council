"""Markdown reporter — writes .council-review.md."""

from __future__ import annotations

from pathlib import Path

from ..schemas import ChairFinding, ChairVerdict, ReviewerOutput, ReviewPack

VERDICT_ICONS = {"PASS": "✅", "PASS_WITH_WARNINGS": "⚠️", "FAIL": "❌"}


def write_markdown_report(
    verdict: ChairVerdict,
    output_path: str | Path = ".council-review.md",
    review_pack: ReviewPack | None = None,
    reviewer_outputs: list[ReviewerOutput] | None = None,
) -> None:
    """Write the council review as a markdown file."""
    icon = VERDICT_ICONS.get(verdict.verdict, "?")
    lines: list[str] = []

    lines.append(f"# Code Review Council — {icon} {verdict.verdict}")
    lines.append("")

    if verdict.degraded:
        lines.append("> ⚠️ **Degraded run**: integrity issues detected.")
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

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


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

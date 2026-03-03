"""Rich terminal reporter — pretty console output."""

from __future__ import annotations

from rich.console import Console

from ..schemas import ChairFinding, ChairVerdict, GateZeroResult, ReviewerOutput, ReviewPack

console = Console()

VERDICT_STYLES = {
    "PASS": ("bold green", "✅"),
    "PASS_WITH_WARNINGS": ("bold yellow", "⚠️"),
    "FAIL": ("bold red", "❌"),
}

SEVERITY_STYLES = {
    "CRITICAL": "bold red",
    "HIGH": "red",
    "MEDIUM": "yellow",
    "LOW": "dim",
}

_URGENCY_ICONS = {
    "fix_before_merge": "🚫",
    "fix_soon": "⚠️",
    "nice_to_have": "💡",
}

_REC_STYLES = {
    "SAFE_TO_MERGE": ("bold green", "✅"),
    "MERGE_WITH_CAUTION": ("bold yellow", "⚠️"),
    "FIX_BEFORE_MERGE": ("bold red", "🚫"),
}


def print_gate_zero(gate_result: GateZeroResult) -> None:
    """Print Gate Zero results."""
    if gate_result.passed:
        console.print(f"  Stage 0: Gate Zero ........... [green]PASSED[/] ({gate_result.duration_ms}ms)")
    else:
        console.print(f"  Stage 0: Gate Zero ........... [red]FAILED[/] ({gate_result.duration_ms}ms)")
        for f in gate_result.findings:
            loc = f"{f.file}:{f.line_start}" if f.line_start else f.file
            console.print(
                f"    [{SEVERITY_STYLES.get(f.severity, '')}]{f.severity}[/] "
                f"[{f.check}] {loc}"
            )
            console.print(f"          {f.message}")
            if f.suggestion:
                console.print(f"          → {f.suggestion}", style="dim")


def print_review_pack_summary(review_pack: ReviewPack) -> None:
    """Print ReviewPack assembly summary."""
    sym_count = len(review_pack.changed_symbols)
    tested = sum(1 for s in review_pack.changed_symbols if s.has_tests)
    console.print(
        f"  ReviewPack: {sym_count} symbols, {tested} with tests, "
        f"~{review_pack.token_estimate} tokens"
    )
    if review_pack.files_skipped:
        names = ", ".join(review_pack.files_skipped[:3])
        console.print(f"  Skipped {len(review_pack.files_skipped)} files: {names}", style="dim")


def print_reviewer_results(outputs: list[ReviewerOutput]) -> None:
    """Print each reviewer's result."""
    console.print("  Stage 1: Reviewer Panel")
    for i, r in enumerate(outputs):
        prefix = "├─" if i < len(outputs) - 1 else "└─"
        if r.error:
            console.print(
                f"    {prefix} {r.reviewer_id} ({r.model}) ... [red]ERROR[/] ({r.error[:60]})"
            )
        elif r.verdict == "FAIL":
            console.print(
                f"    {prefix} {r.reviewer_id} ({r.model}) ... "
                f"[red]FAIL[/] ({len(r.findings)} findings)"
            )
        elif r.findings:
            console.print(
                f"    {prefix} {r.reviewer_id} ({r.model}) ... "
                f"[yellow]PASS[/] ({len(r.findings)} findings)"
            )
        else:
            console.print(f"    {prefix} {r.reviewer_id} ({r.model}) ... [green]PASS[/]")


def print_finding(f: ChairFinding) -> None:
    """Print a single finding."""
    loc = f.file
    if f.line_start:
        loc += f":{f.line_start}"
        if f.line_end and f.line_end != f.line_start:
            loc += f"-{f.line_end}"
    sym = f" `{f.symbol_name}`" if f.symbol_name else ""

    style = SEVERITY_STYLES.get(f.severity, "")
    console.print(f"\n  [{style}]{f.severity}[/] [{f.category}] {loc}{sym}")
    console.print(f"        {f.description}")
    if f.evidence_ref:
        console.print(f"        Evidence: {f.evidence_ref}", style="dim")
    if f.suggestion:
        console.print(f"        → {f.suggestion}", style="cyan")
    if f.source_reviewers:
        consensus = " (consensus)" if f.consensus else ""
        console.print(
            f"        Source: {', '.join(f.source_reviewers)}{consensus}", style="dim"
        )


def _print_owner_summary(verdict: ChairVerdict) -> None:
    """Print the owner-audience summary block. Called before technical detail."""
    op = verdict.owner_presentation
    if op is None:
        return

    rec_style, rec_icon = _REC_STYLES.get(op.merge_recommendation, ("bold", "?"))
    rec_label = op.merge_recommendation.replace("_", " ")

    console.print()
    console.rule(style="cyan")
    console.print("  [bold cyan]Owner Summary[/]")
    console.print(
        f"  [{rec_style}]{rec_icon} {rec_label}[/]"
        f"  •  Risk: {op.risk_level.upper()}  •  {op.confidence_label}"
    )
    console.print(f"\n  {op.short_summary}", style="italic")
    if op.degraded_warning:
        console.print(f"\n  ⚠️  {op.degraded_warning}", style="yellow")
    if op.findings:
        console.print(f"\n  [bold]Issues ({len(op.findings)}):[/]")
        for f in op.findings:
            icon = _URGENCY_ICONS.get(f.urgency, "•")
            urgency_label = f.urgency.replace("_", " ").upper()
            console.print(f"    {icon}  [{urgency_label}] {f.title}")
    console.rule(style="cyan")


def print_verdict(
    verdict: ChairVerdict,
    review_pack: ReviewPack | None = None,
    reviewer_outputs: list[ReviewerOutput] | None = None,
    gate_result: GateZeroResult | None = None,
    ci_mode: bool = False,
    audience: str = "developer",
) -> None:
    """Print the full council report to terminal."""
    style, icon = VERDICT_STYLES.get(verdict.verdict, ("", "?"))
    files_count = len(review_pack.changed_files) if review_pack else 0
    lines_count = review_pack.total_lines_changed if review_pack else 0

    console.print()
    console.print(
        f"[bold]🏛️  Code Review Council[/] — {files_count} files, {lines_count} lines changed"
    )

    # Owner audience: lead with the plain-English summary, then show technical detail below.
    if audience == "owner" and verdict.owner_presentation is not None:
        _print_owner_summary(verdict)

    if gate_result:
        print_gate_zero(gate_result)

    if review_pack and review_pack.changed_symbols:
        print_review_pack_summary(review_pack)

    if reviewer_outputs:
        print_reviewer_results(reviewer_outputs)

    mode_note = "" if ci_mode else " (advisory)"
    console.print()
    console.rule(style=style.replace("bold ", ""))
    console.print(f"  VERDICT: {icon} {verdict.verdict}{mode_note}", style=style)
    if verdict.degraded:
        console.print("  ⚠️  Degraded run — integrity issues detected:", style="yellow")
        for reason in verdict.degraded_reasons:
            console.print(f"    • {reason}", style="yellow dim")
    console.rule(style=style.replace("bold ", ""))

    if audience == "owner":
        # Skip the raw ChairFinding list for the owner — they have the plain-English
        # summary above.  A short note points to richer output formats.
        n_issues = len(verdict.accepted_blockers) + len(verdict.warnings)
        if n_issues:
            console.print(
                f"\n  ({n_issues} technical finding(s) — use --output-html for full detail)",
                style="dim",
            )
        if verdict.summary:
            console.print(f"\n  {verdict.summary}", style="dim italic")
    else:
        # Developer audience: print full finding list.
        for f in verdict.accepted_blockers:
            print_finding(f)

        for f in verdict.warnings:
            print_finding(f)

        if verdict.dismissed_findings:
            console.print(
                f"\n  ({len(verdict.dismissed_findings)} findings dismissed by Chair)",
                style="dim",
            )

        if verdict.summary:
            console.print(f"\n  {verdict.summary}", style="dim italic")

    console.print()

"""Rich terminal reporter for Council verdicts."""

from __future__ import annotations

from rich.console import Console

from .transport import transport_notes
from ..schemas import ChairFinding, ChairVerdict, GateZeroResult, ReviewerOutput, ReviewPack

console = Console()

VERDICT_STYLES = {
    "PASS": ("bold green", "PASS"),
    "PASS_WITH_WARNINGS": ("bold yellow", "WARN"),
    "FAIL": ("bold red", "FAIL"),
}

SEVERITY_STYLES = {
    "CRITICAL": "bold red",
    "HIGH": "red",
    "MEDIUM": "yellow",
    "LOW": "dim",
}

_URGENCY_ICONS = {
    "fix_before_merge": "[BLOCKER]",
    "fix_soon": "[SOON]",
    "nice_to_have": "[IDEA]",
}

_REC_STYLES = {
    "SAFE_TO_MERGE": ("bold green", "[PASS]"),
    "MERGE_WITH_CAUTION": ("bold yellow", "[WARN]"),
    "FIX_BEFORE_MERGE": ("bold red", "[BLOCK]"),
}


def print_gate_zero(gate_result: GateZeroResult) -> None:
    """Print Gate Zero results."""
    if gate_result.passed:
        console.print(f"  Stage 0: Gate Zero ........... [green]PASSED[/] ({gate_result.duration_ms}ms)")
    else:
        console.print(f"  Stage 0: Gate Zero ........... [red]FAILED[/] ({gate_result.duration_ms}ms)")
        for finding in gate_result.findings:
            loc = f"{finding.file}:{finding.line_start}" if finding.line_start else finding.file
            console.print(
                f"    [{SEVERITY_STYLES.get(finding.severity, '')}]{finding.severity}[/] "
                f"[{finding.check}] {loc}"
            )
            console.print(f"          {finding.message}")
            if finding.suggestion:
                console.print(f"          -> {finding.suggestion}", style="dim")


def print_review_pack_summary(review_pack: ReviewPack) -> None:
    """Print ReviewPack assembly summary."""
    symbol_count = len(review_pack.changed_symbols)
    tested = sum(1 for symbol in review_pack.changed_symbols if symbol.has_tests)
    console.print(
        f"  ReviewPack: {symbol_count} symbols, {tested} with tests, "
        f"~{review_pack.token_estimate} tokens"
    )
    if review_pack.files_skipped:
        names = ", ".join(review_pack.files_skipped[:3])
        console.print(f"  Skipped {len(review_pack.files_skipped)} files: {names}", style="dim")


def print_reviewer_results(outputs: list[ReviewerOutput]) -> None:
    """Print each reviewer's result."""
    console.print("  Stage 1: Reviewer Panel")
    for index, reviewer in enumerate(outputs):
        prefix = "|-" if index < len(outputs) - 1 else "`-"
        mode = (
            f" [{reviewer.output_mode}]"
            if reviewer.output_mode and reviewer.output_mode != "response_format"
            else ""
        )
        if reviewer.error:
            console.print(
                f"    {prefix} {reviewer.reviewer_id} ({reviewer.model}) ... "
                f"[red]ERROR[/]{mode} ({reviewer.error[:60]})"
            )
        elif reviewer.verdict == "FAIL":
            console.print(
                f"    {prefix} {reviewer.reviewer_id} ({reviewer.model}) ... "
                f"[red]FAIL[/]{mode} ({len(reviewer.findings)} findings)"
            )
        elif reviewer.findings:
            console.print(
                f"    {prefix} {reviewer.reviewer_id} ({reviewer.model}) ... "
                f"[yellow]PASS[/]{mode} ({len(reviewer.findings)} findings)"
            )
        else:
            console.print(
                f"    {prefix} {reviewer.reviewer_id} ({reviewer.model}) ... [green]PASS[/]{mode}"
            )


def print_finding(finding: ChairFinding) -> None:
    """Print a single technical finding."""
    loc = finding.file
    if finding.line_start:
        loc += f":{finding.line_start}"
        if finding.line_end and finding.line_end != finding.line_start:
            loc += f"-{finding.line_end}"
    symbol = f" `{finding.symbol_name}`" if finding.symbol_name else ""

    style = SEVERITY_STYLES.get(finding.severity, "")
    console.print(f"\n  [{style}]{finding.severity}[/] [{finding.category}] {loc}{symbol}")
    console.print(f"        {finding.description}")
    if finding.evidence_ref:
        console.print(f"        Evidence: {finding.evidence_ref}", style="dim")
    if finding.suggestion:
        console.print(f"        -> {finding.suggestion}", style="cyan")
    if finding.source_reviewers:
        consensus = " (consensus)" if finding.consensus else ""
        console.print(
            f"        Source: {', '.join(finding.source_reviewers)}{consensus}",
            style="dim",
        )


def _print_owner_summary(verdict: ChairVerdict) -> None:
    """Print the owner-audience summary block."""
    owner_presentation = verdict.owner_presentation
    if owner_presentation is None:
        return

    rec_style, rec_icon = _REC_STYLES.get(owner_presentation.merge_recommendation, ("bold", "?"))
    rec_label = owner_presentation.merge_recommendation.replace("_", " ")

    console.print()
    console.rule(style="cyan")
    console.print("  [bold cyan]Owner Summary[/]")
    console.print(
        f"  [{rec_style}]{rec_icon} {rec_label}[/]"
        f"  -  Risk: {owner_presentation.risk_level.upper()}  -  {owner_presentation.confidence_label}"
    )
    console.print(f"\n  {owner_presentation.short_summary}", style="italic")
    if owner_presentation.degraded_warning:
        console.print(f"\n  [WARN] {owner_presentation.degraded_warning}", style="yellow")
    if owner_presentation.findings:
        console.print(f"\n  [bold]Issues ({len(owner_presentation.findings)}):[/]")
        for finding in owner_presentation.findings:
            icon = _URGENCY_ICONS.get(finding.urgency, "-")
            urgency_label = finding.urgency.replace("_", " ").upper()
            console.print(f"    {icon} [{urgency_label}] {finding.title}")
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
        f"[bold]Code Review Council[/] - {files_count} files, {lines_count} lines changed"
    )

    if audience == "owner" and verdict.owner_presentation is not None:
        _print_owner_summary(verdict)

    if gate_result:
        print_gate_zero(gate_result)

    if review_pack and review_pack.changed_symbols:
        print_review_pack_summary(review_pack)

    if reviewer_outputs:
        print_reviewer_results(reviewer_outputs)

    notes = transport_notes(verdict, reviewer_outputs)
    if notes:
        console.print("  Transport Notes")
        for note in notes:
            console.print(f"    - {note}", style="dim")

    mode_note = "" if ci_mode else " (advisory)"
    console.print()
    console.rule(style=style.replace("bold ", ""))
    console.print(f"  VERDICT: {icon} {verdict.verdict}{mode_note}", style=style)
    if verdict.degraded:
        console.print("  [WARN] Degraded run - integrity issues detected:", style="yellow")
        for reason in verdict.degraded_reasons:
            console.print(f"    - {reason}", style="yellow dim")
    console.rule(style=style.replace("bold ", ""))

    if audience == "owner":
        issue_count = len(verdict.accepted_blockers) + len(verdict.warnings)
        if issue_count:
            console.print(
                f"\n  ({issue_count} technical finding(s) - use --output-html for full detail)",
                style="dim",
            )
        if verdict.summary:
            console.print(f"\n  {verdict.summary}", style="dim italic")
    else:
        for finding in verdict.accepted_blockers:
            print_finding(finding)

        for finding in verdict.warnings:
            print_finding(finding)

        if verdict.dismissed_findings:
            console.print(
                f"\n  ({len(verdict.dismissed_findings)} findings dismissed by Chair)",
                style="dim",
            )

        if verdict.summary:
            console.print(f"\n  {verdict.summary}", style="dim italic")

    console.print()

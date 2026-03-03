"""Rich terminal reporter — pretty console output.

Supports two audience modes:
  - developer (default): full pipeline detail with all findings
  - owner: executive summary with trust signal, top risks, reviewer health
"""

from __future__ import annotations

from typing import Literal

from rich.console import Console

from ..chair import owner_summary
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


def print_owner_summary(
    verdict: ChairVerdict,
    reviewer_outputs: list[ReviewerOutput] | None = None,
) -> None:
    """Print an owner-audience executive summary to the terminal."""
    summary = owner_summary(verdict, reviewer_outputs)
    trust = summary["trust_signal"]
    trust_styles = {"trusted": "bold green", "caution": "bold yellow", "untrusted": "bold red"}
    trust_icons = {"trusted": "\u2705", "caution": "\u26a0\ufe0f", "untrusted": "\u274c"}
    t_style = trust_styles.get(trust, "")
    t_icon = trust_icons.get(trust, "?")

    console.print()
    console.print("[bold]\U0001f3db\ufe0f  Code Review Council \u2014 Owner Summary[/]")
    console.print()
    console.rule(style=t_style.replace("bold ", ""))
    console.print(f"  {t_icon} {summary['label']}  (trust: {trust})", style=t_style)
    console.rule(style=t_style.replace("bold ", ""))
    console.print(f"\n  {summary['headline']}")
    console.print(f"  Confidence: {summary['confidence']:.0%}", style="dim")

    if summary["degraded"]:
        console.print("\n  Integrity Issues:", style="yellow")
        for reason in verdict.degraded_reasons:
            console.print(f"    \u2022 {reason}", style="yellow dim")

    if summary["top_risks"]:
        console.print("\n  Top Risks:", style="bold")
        for i, risk in enumerate(summary["top_risks"], 1):
            console.print(f"    {i}. {risk}")

    if summary["reviewer_health"]:
        console.print("\n  Reviewers:", style="dim")
        for rh in summary["reviewer_health"]:
            icon = "\u2705" if rh["status"] == "ok" else "\u26a0\ufe0f"
            console.print(f"    {icon} {rh['id']}: {rh['status']}", style="dim")

    console.print()


def print_verdict(
    verdict: ChairVerdict,
    review_pack: ReviewPack | None = None,
    reviewer_outputs: list[ReviewerOutput] | None = None,
    gate_result: GateZeroResult | None = None,
    ci_mode: bool = False,
    audience: Literal["developer", "owner"] = "developer",
) -> None:
    """Print the full council report to terminal.

    When audience is "owner", the owner summary is printed first (leading),
    followed by the standard developer output for completeness.
    """
    if audience == "owner":
        print_owner_summary(verdict, reviewer_outputs)

    style, icon = VERDICT_STYLES.get(verdict.verdict, ("", "?"))
    files_count = len(review_pack.changed_files) if review_pack else 0
    lines_count = review_pack.total_lines_changed if review_pack else 0

    console.print()
    console.print(
        f"[bold]\U0001f3db\ufe0f  Code Review Council[/] \u2014 {files_count} files, {lines_count} lines changed"
    )

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
        console.print("  \u26a0\ufe0f  Degraded run \u2014 integrity issues detected:", style="yellow")
        for reason in verdict.degraded_reasons:
            console.print(f"    \u2022 {reason}", style="yellow dim")
    console.rule(style=style.replace("bold ", ""))

    for f in verdict.accepted_blockers:
        print_finding(f)

    for f in verdict.warnings:
        print_finding(f)

    if verdict.dismissed_findings:
        console.print(
            f"\n  ({len(verdict.dismissed_findings)} findings dismissed by Chair)", style="dim"
        )

    if verdict.summary:
        console.print(f"\n  {verdict.summary}", style="dim italic")

    console.print()

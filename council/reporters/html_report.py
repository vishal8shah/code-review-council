"""HTML reporter - writes a standalone static HTML report."""

from __future__ import annotations

import html
from pathlib import Path

from ..guidance import (
    build_engineer_review_note,
    build_fix_prompt,
    build_review_next_steps,
    build_verification_step,
)
from .transport import reviewer_output_mode, transport_notes
from ..schemas import (
    ChairFinding,
    ChairVerdict,
    OwnerFindingView,
    OwnerPresentation,
    ReviewerOutput,
    ReviewPack,
)

VERDICT_COLORS = {
    "PASS": ("#16a34a", "#dcfce7", "PASS"),
    "PASS_WITH_WARNINGS": ("#ca8a04", "#fef9c3", "PASS WITH WARNINGS"),
    "FAIL": ("#dc2626", "#fee2e2", "FAIL"),
}

SEVERITY_COLORS = {
    "CRITICAL": ("#991b1b", "#fee2e2"),
    "HIGH": ("#c2410c", "#ffedd5"),
    "MEDIUM": ("#a16207", "#fef9c3"),
    "LOW": ("#374151", "#f3f4f6"),
}

URGENCY_LABELS = {
    "fix_before_merge": ("[BLOCKER]", "Fix before merge", "#fee2e2", "#991b1b"),
    "fix_soon": ("[SOON]", "Fix soon", "#fef9c3", "#a16207"),
    "nice_to_have": ("[IDEA]", "Nice to have", "#f0f9ff", "#0369a1"),
}

MERGE_REC_DISPLAY = {
    "SAFE_TO_MERGE": ("[PASS]", "SAFE TO MERGE", "#16a34a", "#dcfce7"),
    "MERGE_WITH_CAUTION": ("[WARN]", "MERGE WITH CAUTION", "#ca8a04", "#fef9c3"),
    "FIX_BEFORE_MERGE": ("[FAIL]", "FIX BEFORE MERGE", "#dc2626", "#fee2e2"),
}

RISK_COLORS = {
    "low": ("#16a34a", "#dcfce7"),
    "medium": ("#ca8a04", "#fef9c3"),
    "high": ("#c2410c", "#ffedd5"),
    "critical": ("#dc2626", "#fee2e2"),
}

_CSS = """
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 15px;
    line-height: 1.6;
    color: #111827;
    background: #f9fafb;
  }
  .page { max-width: 860px; margin: 0 auto; padding: 32px 20px 64px; }
  .header { margin-bottom: 32px; }
  .header h1 { font-size: 22px; font-weight: 700; color: #111827; }
  .header .subtitle { color: #6b7280; font-size: 13px; margin-top: 4px; }
  .verdict-banner {
    border-radius: 10px;
    padding: 24px 28px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 20px;
  }
  .verdict-icon { font-size: 20px; line-height: 1; font-weight: 700; }
  .verdict-text h2 { font-size: 20px; font-weight: 700; letter-spacing: 0.03em; }
  .verdict-text p { font-size: 14px; margin-top: 6px; opacity: 0.85; }
  .meta-row {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 24px;
    align-items: center;
  }
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 12px;
    border-radius: 9999px;
    font-size: 13px;
    font-weight: 600;
  }
  .summary-box {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 28px;
    color: #374151;
    font-size: 15px;
  }
  .summary-box p + p { margin-top: 10px; }
  .degraded-warning {
    background: #fef3c7;
    border: 1px solid #fcd34d;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 20px;
    font-size: 13px;
    color: #92400e;
  }
  .section-header {
    font-size: 17px;
    font-weight: 700;
    color: #111827;
    margin: 32px 0 16px;
    padding-bottom: 8px;
    border-bottom: 2px solid #e5e7eb;
  }
  .finding-card {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    margin-bottom: 16px;
    overflow: hidden;
  }
  .finding-card-header {
    padding: 14px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }
  .finding-card-title { font-weight: 600; font-size: 15px; flex: 1; min-width: 200px; }
  .finding-card-body { padding: 0 20px 20px; }
  .finding-divider { height: 1px; background: #f3f4f6; margin: 0 0 16px; }
  .owner-field { margin-bottom: 14px; }
  .owner-field-label {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #6b7280;
    margin-bottom: 4px;
  }
  .owner-field-value { color: #111827; font-size: 14px; }
  .fix-prompt {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 12px 14px;
    font-family: "SFMono-Regular", Consolas, monospace;
    font-size: 13px;
    color: #0f172a;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .involve-engineer {
    background: #f0f9ff;
    border: 1px solid #bae6fd;
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 13px;
    color: #0c4a6e;
  }
  .tech-field { margin-bottom: 10px; font-size: 14px; }
  .tech-field strong { color: #374151; }
  .tech-meta { font-size: 12px; color: #6b7280; margin-top: 8px; }
  .evidence-box {
    background: #f8fafc;
    border-left: 3px solid #94a3b8;
    padding: 8px 12px;
    font-family: monospace;
    font-size: 12px;
    color: #475569;
    margin-top: 8px;
    white-space: pre-wrap;
    word-break: break-word;
  }
  details { margin-bottom: 16px; }
  summary {
    cursor: pointer;
    font-weight: 600;
    color: #374151;
    padding: 10px 0;
    font-size: 14px;
    list-style: none;
  }
  summary::-webkit-details-marker { display: none; }
  summary::before { content: "> "; font-size: 11px; }
  details[open] summary::before { content: "v "; }
  .reviewer-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .reviewer-table th, .reviewer-table td {
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid #e5e7eb;
  }
  .reviewer-table th { font-weight: 600; color: #6b7280; background: #f9fafb; }
  .copy-btn {
    margin-top: 8px;
    display: inline-block;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
    color: #0369a1;
    background: #f0f9ff;
    border: 1px solid #bae6fd;
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.15s;
  }
  .copy-btn:hover { background: #e0f2fe; }
  .inline-warning {
    background: #fef3c7;
    border: 1px solid #fcd34d;
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 13px;
    color: #92400e;
    margin-bottom: 16px;
  }
  .engineer-banner {
    background: #f0f9ff;
    border: 1px solid #7dd3fc;
    border-left: 4px solid #0369a1;
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 13px;
    color: #0c4a6e;
    margin-bottom: 20px;
  }
  .finding-card.urgency-block { border-left: 4px solid #dc2626; }
  .finding-card.urgency-soon { border-left: 4px solid #ca8a04; }
  .next-steps {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 24px;
    color: #334155;
  }
  .next-steps ul { margin: 8px 0 0 18px; }
  .footer {
    margin-top: 48px;
    padding-top: 16px;
    border-top: 1px solid #e5e7eb;
    font-size: 12px;
    color: #9ca3af;
  }
"""

_COPY_JS = """
<script>
function _councilCopy(btn) {
  var text = btn.getAttribute('data-prompt');
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function() {
      btn.textContent = 'Copied';
      setTimeout(function() { btn.textContent = 'Copy fix prompt'; }, 2000);
    }, function() {
      btn.textContent = 'Copy failed';
      setTimeout(function() { btn.textContent = 'Copy fix prompt'; }, 2000);
    });
  } else {
    btn.textContent = 'Copy fix prompt (use Ctrl+C)';
    setTimeout(function() { btn.textContent = 'Copy fix prompt'; }, 2000);
  }
}
</script>
"""


def _e(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(str(text))


def _badge(text: str, bg: str, fg: str) -> str:
    """Render a pill-style badge."""
    return (
        f'<span class="badge" style="background:{bg};color:{fg}">'
        f"{_e(text)}</span>"
    )


def _severity_badge(severity: str) -> str:
    """Render a severity badge."""
    fg, bg = SEVERITY_COLORS.get(severity, ("#374151", "#f3f4f6"))
    return _badge(severity, bg, fg)


def _owner_finding_card(finding: OwnerFindingView) -> str:
    """Render an owner-facing finding card."""
    icon, label, bg, fg = URGENCY_LABELS.get(
        finding.urgency, ("[INFO]", finding.urgency, "#f3f4f6", "#374151")
    )
    urgency_class = ""
    if finding.urgency == "fix_before_merge":
        urgency_class = " urgency-block"
    elif finding.urgency == "fix_soon":
        urgency_class = " urgency-soon"

    involve_html = ""
    if finding.involve_engineer:
        involve_html = (
            '<div class="owner-field">'
            '<div class="owner-field-label">When to involve an engineer</div>'
            f'<div class="involve-engineer">{_e(finding.involve_engineer)}</div>'
            "</div>"
        )

    prompt_attr = html.escape(finding.fix_prompt, quote=True)
    return f"""
<div class="finding-card{urgency_class}">
  <div class="finding-card-header" style="background:{bg}">
    <span style="font-size:16px;font-weight:700">{icon}</span>
    <span class="finding-card-title" style="color:{fg}">{_e(finding.title)}</span>
    {_badge(label, bg, fg)}
    {_badge(finding.severity_label, bg, fg)}
  </div>
  <div class="finding-divider"></div>
  <div class="finding-card-body">
    <div class="owner-field">
      <div class="owner-field-label">What is wrong</div>
      <div class="owner-field-value">{_e(finding.plain_explanation)}</div>
    </div>
    <div class="owner-field">
      <div class="owner-field-label">Why it matters</div>
      <div class="owner-field-value">{_e(finding.why_it_matters)}</div>
    </div>
    <div class="owner-field">
      <div class="owner-field-label">Fix prompt</div>
      <div class="fix-prompt">{_e(finding.fix_prompt)}</div>
      <button class="copy-btn" data-prompt="{prompt_attr}" onclick="_councilCopy(this)">Copy fix prompt</button>
    </div>
    <div class="owner-field">
      <div class="owner-field-label">What to test after fixing</div>
      <div class="owner-field-value">{_e(finding.test_after_fix)}</div>
    </div>
    {involve_html}
  </div>
</div>"""


def _tech_finding_card(finding: ChairFinding) -> str:
    """Render a technical finding card."""
    fg, bg = SEVERITY_COLORS.get(finding.severity, ("#374151", "#f3f4f6"))
    location = finding.file
    if finding.line_start:
        location += f":{finding.line_start}"
        if finding.line_end and finding.line_end != finding.line_start:
            location += f"-{finding.line_end}"

    symbol_html = ""
    if finding.symbol_name:
        symbol_html = f' &mdash; <code>{_e(finding.symbol_name)}</code>'

    evidence_html = ""
    if finding.evidence_ref:
        evidence_html = f'<div class="evidence-box">{_e(finding.evidence_ref)}</div>'

    reasoning_html = ""
    if finding.chair_reasoning:
        reasoning_html = f'<div class="tech-meta">Chair: {_e(finding.chair_reasoning)}</div>'

    sources_html = ""
    if finding.source_reviewers:
        consensus = " (consensus)" if finding.consensus else ""
        sources_html = (
            f'<div class="tech-meta">Source: {_e(", ".join(finding.source_reviewers))}'
            f"{consensus}</div>"
        )

    suggestion_html = ""
    if finding.suggestion:
        suggestion_html = (
            f'<div class="tech-field"><strong>Fix:</strong> {_e(finding.suggestion)}</div>'
        )
    fix_prompt = build_fix_prompt(finding)
    guidance_html = f"""
    <div class="tech-field"><strong>Fix prompt:</strong></div>
    <div class="fix-prompt">{_e(fix_prompt)}</div>
    <div class="tech-field" style="margin-top:12px"><strong>Verify after fixing:</strong> {_e(build_verification_step(finding))}</div>
    """
    engineer_note = build_engineer_review_note(finding)
    if engineer_note:
        guidance_html += f'<div class="involve-engineer">{_e(engineer_note)}</div>'

    return f"""
<div class="finding-card">
  <div class="finding-card-header" style="background:{bg}">
    {_severity_badge(finding.severity)}
    <span class="badge" style="background:{bg};color:{fg}">{_e(finding.category)}</span>
    <span class="finding-card-title" style="color:{fg}">
      <code style="font-size:13px">{_e(location)}</code>{symbol_html}
    </span>
  </div>
  <div class="finding-divider"></div>
  <div class="finding-card-body">
    <div class="tech-field">{_e(finding.description)}</div>
    {suggestion_html}
    {guidance_html}
    {evidence_html}
    {reasoning_html}
    {sources_html}
  </div>
</div>"""


def _owner_report_html(
    verdict: ChairVerdict,
    owner_presentation: OwnerPresentation,
    review_pack: ReviewPack | None,
    reviewer_outputs: list[ReviewerOutput] | None,
) -> str:
    """Build the owner-audience HTML report."""
    notes = transport_notes(verdict, reviewer_outputs)
    icon, rec_label, fg, bg = MERGE_REC_DISPLAY.get(
        owner_presentation.merge_recommendation,
        ("?", owner_presentation.merge_recommendation, "#374151", "#f3f4f6"),
    )
    risk_fg, risk_bg = RISK_COLORS.get(owner_presentation.risk_level, ("#374151", "#f3f4f6"))

    degraded_html = ""
    if owner_presentation.degraded_warning:
        degraded_html = (
            f'<div class="degraded-warning">[WARN] {_e(owner_presentation.degraded_warning)}</div>'
        )

    transport_html = ""
    if notes:
        items = "".join(f"<li>{_e(note)}</li>" for note in notes)
        transport_html = (
            '<div class="inline-warning"><strong>Transport notes:</strong>'
            f"<ul style=\"margin:8px 0 0 16px\">{items}</ul></div>"
        )

    next_steps_html = _next_steps_html(verdict)

    has_tech_findings = bool(verdict.accepted_blockers or verdict.warnings)
    has_engineer_involvement = owner_presentation.findings and any(
        finding.involve_engineer for finding in owner_presentation.findings
    )
    engineer_banner_html = ""
    if has_engineer_involvement:
        engineer_banner_html = (
            '<div class="engineer-banner">'
            '[ENGINEER] <strong>Developer involvement needed</strong>: One or more issues '
            'in this review require a developer to review the fix before merging. See the '
            '"When to involve an engineer" note on the relevant issue card(s).'
            "</div>"
        )

    if owner_presentation.findings:
        owner_findings_html = (
            '<div class="section-header">Issues Found</div>'
            f"{engineer_banner_html}"
            + "".join(_owner_finding_card(finding) for finding in owner_presentation.findings)
        )
    elif owner_presentation.merge_recommendation == "SAFE_TO_MERGE" and not has_tech_findings:
        owner_findings_html = (
            '<div class="section-header">Issues Found</div>'
            '<div class="summary-box"><p>No issues require your attention.</p></div>'
        )
    else:
        owner_findings_html = (
            '<div class="section-header">Issues Found</div>'
            '<div class="inline-warning">[WARN] The owner-friendly issue cards could not '
            'be generated for this report. The technical appendix below contains the full '
            'list of accepted findings from the review.</div>'
        )

    tech_html = ""
    if verdict.accepted_blockers or verdict.warnings or verdict.dismissed_findings:
        blocker_cards = "".join(_tech_finding_card(finding) for finding in verdict.accepted_blockers)
        warning_cards = "".join(_tech_finding_card(finding) for finding in verdict.warnings)
        dismissed_cards = "".join(
            _tech_finding_card(finding) for finding in verdict.dismissed_findings
        )
        blockers_section = (
            "<div style='margin-bottom:8px;font-weight:600;color:#374151'>"
            f"Blockers ({len(verdict.accepted_blockers)})</div>{blocker_cards}"
        ) if verdict.accepted_blockers else ""
        warnings_section = (
            "<div style='margin-bottom:8px;font-weight:600;color:#374151'>"
            f"Warnings ({len(verdict.warnings)})</div>{warning_cards}"
        ) if verdict.warnings else ""
        dismissed_section = (
            "<div style='margin-bottom:8px;font-weight:600;color:#374151'>"
            f"Dismissed ({len(verdict.dismissed_findings)})</div>{dismissed_cards}"
        ) if verdict.dismissed_findings else ""
        tech_html = f"""
<div class="section-header">Technical Appendix</div>
<details>
  <summary>Technical findings detail (for developer reference)</summary>
  <div style="margin-top:12px">
    {blockers_section}
    {warnings_section}
    {dismissed_section}
  </div>
</details>
<details>
  <summary>Chair rationale</summary>
  <div style="margin-top:12px;font-size:14px;color:#374151;white-space:pre-wrap">{_e(verdict.rationale)}</div>
</details>"""

    reviewer_html = ""
    if reviewer_outputs:
        rows = "".join(
            f"<tr><td>{_e(reviewer.reviewer_id)}</td>"
            f"<td><code style='font-size:12px'>{_e(reviewer.model)}</code></td>"
            f"<td>{_e(reviewer.verdict)}</td>"
            f"<td>{len(reviewer.findings)}</td>"
            f"<td>{_e(reviewer_output_mode(reviewer))}</td>"
            f"<td style='color:#dc2626'>{_e(reviewer.error or '')}</td></tr>"
            for reviewer in reviewer_outputs
        )
        reviewer_html = f"""
<details>
  <summary>Reviewer panel ({len(reviewer_outputs)} reviewers)</summary>
  <table class="reviewer-table" style="margin-top:12px">
    <thead><tr><th>Reviewer</th><th>Model</th><th>Verdict</th><th>Findings</th><th>Output mode</th><th>Error</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</details>"""

    meta_html = ""
    if review_pack:
        files = len(review_pack.changed_files)
        lines_changed = review_pack.total_lines_changed
        languages = ", ".join(review_pack.languages_detected) or "unknown"
        meta_html = f"""
<details>
  <summary>Review metadata</summary>
  <div style="margin-top:12px;font-size:14px;color:#374151">
    <div>Files changed: {files}</div>
    <div>Lines changed: {lines_changed}</div>
    <div>Languages: {_e(languages)}</div>
  </div>
</details>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Code Review Council - Owner Report</title>
  <style>{_CSS}</style>
</head>
<body>
<div class="page">
  <div class="header">
    <h1>Code Review Council</h1>
    <div class="subtitle">Owner report &mdash; plain-English review summary</div>
  </div>

  <div class="verdict-banner" style="background:{bg};color:{fg}">
    <div class="verdict-icon">{icon}</div>
    <div class="verdict-text">
      <h2>{_e(rec_label)}</h2>
      <p>{_e(owner_presentation.headline)}</p>
    </div>
  </div>

  <div class="meta-row">
    {_badge("Risk: " + owner_presentation.risk_level.upper(), risk_bg, risk_fg)}
    {_badge(owner_presentation.confidence_label, "#f3f4f6", "#374151")}
    {_badge("Technical verdict: " + verdict.verdict, "#f3f4f6", "#374151")}
  </div>

  {degraded_html}
  {transport_html}
  {next_steps_html}

  <div class="summary-box">
    <p>{_e(owner_presentation.short_summary)}</p>
  </div>

  {owner_findings_html}
  {tech_html}
  {reviewer_html}
  {meta_html}

  <div class="footer">
    Generated by Code Review Council &mdash; owner audience &mdash;
    same underlying findings as the developer report
  </div>
</div>
{_COPY_JS}
</body>
</html>"""


def _developer_report_html(
    verdict: ChairVerdict,
    review_pack: ReviewPack | None,
    reviewer_outputs: list[ReviewerOutput] | None,
) -> str:
    """Build the developer-audience HTML report."""
    notes = transport_notes(verdict, reviewer_outputs)
    fg, bg, label = VERDICT_COLORS.get(verdict.verdict, ("#374151", "#f3f4f6", verdict.verdict))
    icon = {
        "PASS": "[PASS]",
        "PASS_WITH_WARNINGS": "[WARN]",
        "FAIL": "[FAIL]",
    }.get(verdict.verdict, "?")

    degraded_html = ""
    if verdict.degraded:
        reasons = "".join(f"<li>{_e(reason)}</li>" for reason in verdict.degraded_reasons)
        degraded_html = (
            '<div class="degraded-warning">[WARN] Degraded run &mdash; integrity issues:'
            f'<ul style="margin:6px 0 0 16px">{reasons}</ul></div>'
        )

    summary_html = ""
    if verdict.summary:
        summary_html = f'<div class="summary-box"><p>{_e(verdict.summary)}</p></div>'

    transport_html = ""
    if notes:
        items = "".join(f"<li>{_e(note)}</li>" for note in notes)
        transport_html = (
            '<div class="inline-warning"><strong>Transport notes:</strong>'
            f"<ul style=\"margin:8px 0 0 16px\">{items}</ul></div>"
        )

    next_steps_html = _next_steps_html(verdict)

    blocker_html = ""
    if verdict.accepted_blockers:
        cards = "".join(_tech_finding_card(finding) for finding in verdict.accepted_blockers)
        blocker_html = f'<div class="section-header">Accepted Blockers</div>{cards}'

    warning_html = ""
    if verdict.warnings:
        cards = "".join(_tech_finding_card(finding) for finding in verdict.warnings)
        warning_html = f'<div class="section-header">Warnings (Non-Blocking)</div>{cards}'

    dismissed_html = ""
    if verdict.dismissed_findings:
        cards = "".join(_tech_finding_card(finding) for finding in verdict.dismissed_findings)
        dismissed_html = f"""
<details>
  <summary>Dismissed findings ({len(verdict.dismissed_findings)})</summary>
  <div style="margin-top:12px">{cards}</div>
</details>"""

    rationale_html = ""
    if verdict.rationale:
        rationale_html = f"""
<details>
  <summary>Chair rationale</summary>
  <div style="margin-top:12px;font-size:14px;color:#374151;white-space:pre-wrap">{_e(verdict.rationale)}</div>
</details>"""

    reviewer_html = ""
    if reviewer_outputs:
        rows = "".join(
            f"<tr><td>{_e(reviewer.reviewer_id)}</td>"
            f"<td><code style='font-size:12px'>{_e(reviewer.model)}</code></td>"
            f"<td>{_e(reviewer.verdict)}</td>"
            f"<td>{len(reviewer.findings)}</td>"
            f"<td>{_e(reviewer_output_mode(reviewer))}</td>"
            f"<td>{reviewer.tokens_used}</td>"
            f"<td style='color:#dc2626'>{_e(reviewer.error or '')}</td></tr>"
            for reviewer in reviewer_outputs
        )
        reviewer_html = f"""
<div class="section-header">Reviewer Panel</div>
<table class="reviewer-table">
  <thead><tr><th>Reviewer</th><th>Model</th><th>Verdict</th><th>Findings</th><th>Output mode</th><th>Tokens</th><th>Error</th></tr></thead>
  <tbody>{rows}</tbody>
</table>"""

    meta_html = ""
    if review_pack:
        files = len(review_pack.changed_files)
        lines_changed = review_pack.total_lines_changed
        languages = ", ".join(review_pack.languages_detected) or "unknown"
        tokens = review_pack.token_estimate
        skipped = ", ".join(review_pack.files_skipped[:5]) or "none"
        meta_html = f"""
<div class="section-header">Review Metadata</div>
<div class="summary-box" style="font-size:14px">
  <div>Files changed: {files} &nbsp;&nbsp; Lines changed: {lines_changed} &nbsp;&nbsp; Token estimate: {tokens}</div>
  <div>Languages: {_e(languages)}</div>
  <div>Skipped: {_e(skipped)}</div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Code Review Council - Developer Report</title>
  <style>{_CSS}</style>
</head>
<body>
<div class="page">
  <div class="header">
    <h1>Code Review Council</h1>
    <div class="subtitle">Developer report &mdash; technical review findings</div>
  </div>

  <div class="verdict-banner" style="background:{bg};color:{fg}">
    <div class="verdict-icon">{icon}</div>
    <div class="verdict-text">
      <h2>{_e(label)}</h2>
      <p>Confidence: {verdict.confidence:.0%} &mdash; Agreement score: {verdict.reviewer_agreement_score:.0%}</p>
    </div>
  </div>

  {degraded_html}
  {transport_html}
  {next_steps_html}
  {summary_html}
  {meta_html}
  {reviewer_html}
  {blocker_html}
  {warning_html}
  {dismissed_html}
  {rationale_html}

  <div class="footer">
    Generated by Code Review Council &mdash; developer audience
  </div>
</div>
</body>
</html>"""


def _next_steps_html(verdict: ChairVerdict) -> str:
    """Render deterministic next steps for the whole review."""
    steps = build_review_next_steps(verdict)
    if not steps:
        return ""
    items = "".join(f"<li>{_e(step)}</li>" for step in steps)
    return f'<div class="next-steps"><strong>Next steps</strong><ul>{items}</ul></div>'


def write_html_report(
    verdict: ChairVerdict,
    output_path: str | Path,
    audience: str = "developer",
    review_pack: ReviewPack | None = None,
    reviewer_outputs: list[ReviewerOutput] | None = None,
) -> None:
    """Write a standalone static HTML report."""
    if audience == "owner" and verdict.owner_presentation is not None:
        content = _owner_report_html(
            verdict=verdict,
            owner_presentation=verdict.owner_presentation,
            review_pack=review_pack,
            reviewer_outputs=reviewer_outputs,
        )
    else:
        content = _developer_report_html(
            verdict=verdict,
            review_pack=review_pack,
            reviewer_outputs=reviewer_outputs,
        )

    Path(output_path).write_text(content, encoding="utf-8")

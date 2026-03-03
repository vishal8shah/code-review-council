"""HTML reporter — writes a standalone static HTML report.

Produces a single self-contained HTML file with no external dependencies.
Suitable for sharing with product owners and semi-technical stakeholders.

Works for both developer and owner audiences:
- owner: rich owner-presentation cards + technical appendix
- developer: technical findings in a clean card layout
"""

from __future__ import annotations

import html
from pathlib import Path

from ..schemas import ChairFinding, ChairVerdict, OwnerFindingView, OwnerPresentation, ReviewerOutput, ReviewPack

# ---------------------------------------------------------------------------
# Verdict display constants
# ---------------------------------------------------------------------------

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
    "fix_before_merge": ("🚫", "Fix before merge", "#fee2e2", "#991b1b"),
    "fix_soon": ("⚠️", "Fix soon", "#fef9c3", "#a16207"),
    "nice_to_have": ("💡", "Nice to have", "#f0f9ff", "#0369a1"),
}

MERGE_REC_DISPLAY = {
    "SAFE_TO_MERGE": ("✅", "SAFE TO MERGE", "#16a34a", "#dcfce7"),
    "MERGE_WITH_CAUTION": ("⚠️", "MERGE WITH CAUTION", "#ca8a04", "#fef9c3"),
    "FIX_BEFORE_MERGE": ("🚫", "FIX BEFORE MERGE", "#dc2626", "#fee2e2"),
}

RISK_COLORS = {
    "low": ("#16a34a", "#dcfce7"),
    "medium": ("#ca8a04", "#fef9c3"),
    "high": ("#c2410c", "#ffedd5"),
    "critical": ("#dc2626", "#fee2e2"),
}

# ---------------------------------------------------------------------------
# Shared CSS
# ---------------------------------------------------------------------------

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

  /* Verdict banner */
  .verdict-banner {
    border-radius: 10px;
    padding: 24px 28px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 20px;
  }
  .verdict-icon { font-size: 36px; line-height: 1; }
  .verdict-text h2 { font-size: 20px; font-weight: 700; letter-spacing: 0.03em; }
  .verdict-text p { font-size: 14px; margin-top: 6px; opacity: 0.85; }

  /* Meta row */
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

  /* Summary box */
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

  /* Degraded warning */
  .degraded-warning {
    background: #fef3c7;
    border: 1px solid #fcd34d;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 20px;
    font-size: 13px;
    color: #92400e;
  }

  /* Section headers */
  .section-header {
    font-size: 17px;
    font-weight: 700;
    color: #111827;
    margin: 32px 0 16px;
    padding-bottom: 8px;
    border-bottom: 2px solid #e5e7eb;
  }

  /* Finding cards */
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

  /* Owner finding layout */
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

  /* Technical finding layout */
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

  /* Appendix / collapsible */
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
  summary::before { content: "▶ "; font-size: 11px; }
  details[open] summary::before { content: "▼ "; }

  /* Reviewer table */
  .reviewer-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .reviewer-table th, .reviewer-table td {
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid #e5e7eb;
  }
  .reviewer-table th { font-weight: 600; color: #6b7280; background: #f9fafb; }

  /* Copy button */
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

  /* Inline warning box (used for empty-state safety) */
  .inline-warning {
    background: #fef3c7;
    border: 1px solid #fcd34d;
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 13px;
    color: #92400e;
    margin-bottom: 16px;
  }

  /* Footer */
  .footer {
    margin-top: 48px;
    padding-top: 16px;
    border-top: 1px solid #e5e7eb;
    font-size: 12px;
    color: #9ca3af;
  }
"""

# Inline JS for copy-to-clipboard.  No external dependencies.
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


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _e(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(str(text))


def _badge(text: str, bg: str, fg: str) -> str:
    return (
        f'<span class="badge" style="background:{bg};color:{fg}">'
        f'{_e(text)}</span>'
    )


def _severity_badge(severity: str) -> str:
    fg, bg = SEVERITY_COLORS.get(severity, ("#374151", "#f3f4f6"))
    return _badge(severity, bg, fg)


def _owner_finding_card(f: OwnerFindingView) -> str:
    icon, label, bg, fg = URGENCY_LABELS.get(
        f.urgency, ("💡", f.urgency, "#f3f4f6", "#374151")
    )
    involve_html = ""
    if f.involve_engineer:
        involve_html = (
            f'<div class="owner-field">'
            f'<div class="owner-field-label">When to involve an engineer</div>'
            f'<div class="involve-engineer">{_e(f.involve_engineer)}</div>'
            f'</div>'
        )
    # data-prompt uses html.escape so the attribute value is safe even if the
    # fix_prompt contains quotes or angle brackets.
    prompt_attr = html.escape(f.fix_prompt, quote=True)
    return f"""
<div class="finding-card">
  <div class="finding-card-header" style="background:{bg}">
    <span style="font-size:20px">{icon}</span>
    <span class="finding-card-title" style="color:{fg}">{_e(f.title)}</span>
    {_badge(label, bg, fg)}
    {_badge(f.severity_label, bg, fg)}
  </div>
  <div class="finding-divider"></div>
  <div class="finding-card-body">
    <div class="owner-field">
      <div class="owner-field-label">What is wrong</div>
      <div class="owner-field-value">{_e(f.plain_explanation)}</div>
    </div>
    <div class="owner-field">
      <div class="owner-field-label">Why it matters</div>
      <div class="owner-field-value">{_e(f.why_it_matters)}</div>
    </div>
    <div class="owner-field">
      <div class="owner-field-label">Fix prompt</div>
      <div class="fix-prompt">{_e(f.fix_prompt)}</div>
      <button class="copy-btn" data-prompt="{prompt_attr}" onclick="_councilCopy(this)">Copy fix prompt</button>
    </div>
    <div class="owner-field">
      <div class="owner-field-label">What to test after fixing</div>
      <div class="owner-field-value">{_e(f.test_after_fix)}</div>
    </div>
    {involve_html}
  </div>
</div>"""


def _tech_finding_card(f: ChairFinding, role: str = "blocker") -> str:
    fg, bg = SEVERITY_COLORS.get(f.severity, ("#374151", "#f3f4f6"))
    loc = f.file
    if f.line_start:
        loc += f":{f.line_start}"
        if f.line_end and f.line_end != f.line_start:
            loc += f"-{f.line_end}"
    sym_html = ""
    if f.symbol_name:
        sym_html = f' &mdash; <code>{_e(f.symbol_name)}</code>'
    evidence_html = ""
    if f.evidence_ref:
        evidence_html = f'<div class="evidence-box">{_e(f.evidence_ref)}</div>'
    reasoning_html = ""
    if f.chair_reasoning:
        reasoning_html = (
            f'<div class="tech-meta">Chair: {_e(f.chair_reasoning)}</div>'
        )
    sources_html = ""
    if f.source_reviewers:
        sources_html = (
            f'<div class="tech-meta">Source: {_e(", ".join(f.source_reviewers))}'
            f'{"  (consensus)" if f.consensus else ""}</div>'
        )
    suggestion_html = ""
    if f.suggestion:
        suggestion_html = (
            f'<div class="tech-field"><strong>Fix:</strong> {_e(f.suggestion)}</div>'
        )
    return f"""
<div class="finding-card">
  <div class="finding-card-header" style="background:{bg}">
    {_severity_badge(f.severity)}
    <span class="badge" style="background:{bg};color:{fg}">{_e(f.category)}</span>
    <span class="finding-card-title" style="color:{fg}">
      <code style="font-size:13px">{_e(loc)}</code>{sym_html}
    </span>
  </div>
  <div class="finding-divider"></div>
  <div class="finding-card-body">
    <div class="tech-field">{_e(f.description)}</div>
    {suggestion_html}
    {evidence_html}
    {reasoning_html}
    {sources_html}
  </div>
</div>"""


# ---------------------------------------------------------------------------
# Owner report HTML
# ---------------------------------------------------------------------------

def _owner_report_html(
    verdict: ChairVerdict,
    op: OwnerPresentation,
    review_pack: ReviewPack | None,
    reviewer_outputs: list[ReviewerOutput] | None,
) -> str:
    """Build the full owner-audience HTML report."""
    icon, rec_label, fg, bg = MERGE_REC_DISPLAY.get(
        op.merge_recommendation, ("?", op.merge_recommendation, "#374151", "#f3f4f6")
    )
    risk_fg, risk_bg = RISK_COLORS.get(op.risk_level, ("#374151", "#f3f4f6"))

    degraded_html = ""
    if op.degraded_warning:
        degraded_html = (
            f'<div class="degraded-warning">⚠️ {_e(op.degraded_warning)}</div>'
        )

    # Owner finding cards.
    # Safety rule: only show "no issues" when the recommendation is SAFE_TO_MERGE
    # AND there are genuinely no technical findings.  Any other combination would
    # be contradictory and misleading.
    has_tech_findings = bool(verdict.accepted_blockers or verdict.warnings)
    owner_findings_html = ""
    if op.findings:
        owner_findings_html = (
            '<div class="section-header">Issues Found</div>'
            + "".join(_owner_finding_card(f) for f in op.findings)
        )
    elif op.merge_recommendation == "SAFE_TO_MERGE" and not has_tech_findings:
        owner_findings_html = (
            '<div class="section-header">Issues Found</div>'
            '<div class="summary-box"><p>No issues require your attention.</p></div>'
        )
    else:
        # Empty findings but a non-safe recommendation or known technical findings —
        # show a fallback warning rather than a contradictory "all clear" message.
        owner_findings_html = (
            '<div class="section-header">Issues Found</div>'
            '<div class="inline-warning">⚠️ This report could not render detailed '
            'owner issue cards. Please review the technical appendix below for the '
            'full list of accepted findings.</div>'
        )

    # Technical appendix
    tech_html = ""
    if verdict.accepted_blockers or verdict.warnings or verdict.dismissed_findings:
        blocker_cards = "".join(
            _tech_finding_card(f, "blocker") for f in verdict.accepted_blockers
        )
        warning_cards = "".join(
            _tech_finding_card(f, "warning") for f in verdict.warnings
        )
        dismissed_cards = "".join(
            _tech_finding_card(f, "dismissed") for f in verdict.dismissed_findings
        )
        blockers_section = (
            f"<div style='margin-bottom:8px;font-weight:600;color:#374151'>Blockers ({len(verdict.accepted_blockers)})</div>"
            + blocker_cards
        ) if verdict.accepted_blockers else ""
        warnings_section = (
            f"<div style='margin-bottom:8px;font-weight:600;color:#374151'>Warnings ({len(verdict.warnings)})</div>"
            + warning_cards
        ) if verdict.warnings else ""
        dismissed_section = (
            f"<div style='margin-bottom:8px;font-weight:600;color:#374151'>Dismissed ({len(verdict.dismissed_findings)})</div>"
            + dismissed_cards
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

    # Reviewer table
    reviewer_html = ""
    if reviewer_outputs:
        rows = "".join(
            f"<tr><td>{_e(r.reviewer_id)}</td><td><code style='font-size:12px'>{_e(r.model)}</code></td>"
            f"<td>{_e(r.verdict)}</td><td>{len(r.findings)}</td>"
            f"<td style='color:#dc2626'>{_e(r.error or '')}</td></tr>"
            for r in reviewer_outputs
        )
        reviewer_html = f"""
<details>
  <summary>Reviewer panel ({len(reviewer_outputs)} reviewers)</summary>
  <table class="reviewer-table" style="margin-top:12px">
    <thead><tr><th>Reviewer</th><th>Model</th><th>Verdict</th><th>Findings</th><th>Error</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</details>"""

    # Metadata
    meta_html = ""
    if review_pack:
        files = len(review_pack.changed_files)
        lines = review_pack.total_lines_changed
        langs = ", ".join(review_pack.languages_detected) or "unknown"
        meta_html = f"""
<details>
  <summary>Review metadata</summary>
  <div style="margin-top:12px;font-size:14px;color:#374151">
    <div>Files changed: {files}</div>
    <div>Lines changed: {lines}</div>
    <div>Languages: {_e(langs)}</div>
  </div>
</details>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Code Review Council — Owner Report</title>
  <style>{_CSS}</style>
</head>
<body>
<div class="page">
  <div class="header">
    <h1>🏛️ Code Review Council</h1>
    <div class="subtitle">Owner report &mdash; plain-English review summary</div>
  </div>

  <div class="verdict-banner" style="background:{bg};color:{fg}">
    <div class="verdict-icon">{icon}</div>
    <div class="verdict-text">
      <h2>{_e(rec_label)}</h2>
      <p>{_e(op.headline)}</p>
    </div>
  </div>

  <div class="meta-row">
    {_badge("Risk: " + op.risk_level.upper(), risk_bg, risk_fg)}
    {_badge(op.confidence_label, "#f3f4f6", "#374151")}
    {_badge("Technical verdict: " + verdict.verdict, "#f3f4f6", "#374151")}
  </div>

  {degraded_html}

  <div class="summary-box">
    <p>{_e(op.short_summary)}</p>
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


# ---------------------------------------------------------------------------
# Developer report HTML
# ---------------------------------------------------------------------------

def _developer_report_html(
    verdict: ChairVerdict,
    review_pack: ReviewPack | None,
    reviewer_outputs: list[ReviewerOutput] | None,
) -> str:
    """Build a clean technical HTML report for developer audience."""
    fg, bg, label = VERDICT_COLORS.get(verdict.verdict, ("#374151", "#f3f4f6", verdict.verdict))

    icon = {"PASS": "✅", "PASS_WITH_WARNINGS": "⚠️", "FAIL": "❌"}.get(verdict.verdict, "?")

    degraded_html = ""
    if verdict.degraded:
        reasons = "".join(f"<li>{_e(r)}</li>" for r in verdict.degraded_reasons)
        degraded_html = (
            f'<div class="degraded-warning">⚠️ Degraded run — integrity issues:<ul style="margin:6px 0 0 16px">'
            f'{reasons}</ul></div>'
        )

    summary_html = ""
    if verdict.summary:
        summary_html = f'<div class="summary-box"><p>{_e(verdict.summary)}</p></div>'

    blocker_html = ""
    if verdict.accepted_blockers:
        cards = "".join(_tech_finding_card(f, "blocker") for f in verdict.accepted_blockers)
        blocker_html = f'<div class="section-header">Accepted Blockers</div>{cards}'

    warning_html = ""
    if verdict.warnings:
        cards = "".join(_tech_finding_card(f, "warning") for f in verdict.warnings)
        warning_html = f'<div class="section-header">Warnings (Non-Blocking)</div>{cards}'

    dismissed_html = ""
    if verdict.dismissed_findings:
        cards = "".join(_tech_finding_card(f, "dismissed") for f in verdict.dismissed_findings)
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
            f"<tr><td>{_e(r.reviewer_id)}</td><td><code style='font-size:12px'>{_e(r.model)}</code></td>"
            f"<td>{_e(r.verdict)}</td><td>{len(r.findings)}</td><td>{r.tokens_used}</td>"
            f"<td style='color:#dc2626'>{_e(r.error or '')}</td></tr>"
            for r in reviewer_outputs
        )
        reviewer_html = f"""
<div class="section-header">Reviewer Panel</div>
<table class="reviewer-table">
  <thead><tr><th>Reviewer</th><th>Model</th><th>Verdict</th><th>Findings</th><th>Tokens</th><th>Error</th></tr></thead>
  <tbody>{rows}</tbody>
</table>"""

    meta_html = ""
    if review_pack:
        files = len(review_pack.changed_files)
        lines = review_pack.total_lines_changed
        langs = ", ".join(review_pack.languages_detected) or "unknown"
        tokens = review_pack.token_estimate
        skipped = ", ".join(review_pack.files_skipped[:5]) or "none"
        meta_html = f"""
<div class="section-header">Review Metadata</div>
<div class="summary-box" style="font-size:14px">
  <div>Files changed: {files} &nbsp;&nbsp; Lines changed: {lines} &nbsp;&nbsp; Token estimate: {tokens}</div>
  <div>Languages: {_e(langs)}</div>
  <div>Skipped: {_e(skipped)}</div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Code Review Council — Developer Report</title>
  <style>{_CSS}</style>
</head>
<body>
<div class="page">
  <div class="header">
    <h1>🏛️ Code Review Council</h1>
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_html_report(
    verdict: ChairVerdict,
    output_path: str | Path,
    audience: str = "developer",
    review_pack: ReviewPack | None = None,
    reviewer_outputs: list[ReviewerOutput] | None = None,
) -> None:
    """Write a standalone static HTML report.

    Args:
        verdict: The ChairVerdict from council synthesis.
        output_path: File path to write the HTML report to.
        audience: "developer" or "owner". Owner audience uses OwnerPresentation
                  if available on verdict.owner_presentation; falls back to
                  developer layout otherwise.
        review_pack: Optional ReviewPack for metadata sections.
        reviewer_outputs: Optional list of reviewer outputs for the panel table.
    """
    if audience == "owner" and verdict.owner_presentation is not None:
        content = _owner_report_html(
            verdict=verdict,
            op=verdict.owner_presentation,
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

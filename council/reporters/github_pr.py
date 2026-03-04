"""GitHub PR reporter: sticky comment + workflow annotations."""

from __future__ import annotations

import json
import os
import sys
from urllib import error, request

from ..schemas import ChairVerdict, ReviewerOutput

MARKER = "<!-- council-review-verdict -->"
MAX_ERRORS = 10
MAX_WARNINGS = 10


def _sanitize_annotation_message(message: str) -> str:
    """Sanitize message text for GitHub workflow command format."""
    return message.replace("\r", " ").replace("\n", " ").replace("::", ";;")


def _build_comment_body(verdict: ChairVerdict, reviewer_outputs: list[ReviewerOutput] | None = None) -> str:
    lines = [
        MARKER,
        "## 🏛️ Code Review Council",
        f"**Overall verdict:** `{verdict.verdict}` (confidence: {verdict.confidence:.2f})",
        "",
        verdict.summary,
    ]

    if verdict.degraded and verdict.degraded_reasons:
        lines.extend(["", "### ⚠️ Degraded integrity signals"])
        for reason in verdict.degraded_reasons:
            lines.append(f"- {reason}")

    if verdict.accepted_blockers:
        lines.extend(["", "### ❌ Accepted blockers"])
        for f in verdict.accepted_blockers:
            loc = f"`{f.file}:{f.line_start}`" if f.line_start else f"`{f.file}`"
            sug = f" — _Suggestion_: {f.suggestion}" if f.suggestion else ""
            lines.append(f"- **[{f.severity}]** {loc} {f.description}{sug}")

    if verdict.warnings:
        lines.extend(["", "### ⚠️ Accepted warnings"])
        for f in verdict.warnings:
            loc = f"`{f.file}:{f.line_start}`" if f.line_start else f"`{f.file}`"
            sug = f" — _Suggestion_: {f.suggestion}" if f.suggestion else ""
            lines.append(f"- **[{f.severity}]** {loc} {f.description}{sug}")

    if reviewer_outputs:
        lines.extend([
            "",
            "### Reviewer panel",
            "| Reviewer | Verdict | Findings | Error |",
            "|---|---:|---:|---|",
        ])
        for r in reviewer_outputs:
            lines.append(f"| `{r.reviewer_id}` | {r.verdict} | {len(r.findings)} | {r.error or ''} |")

    return "\n".join(lines) + "\n"


def _emit_annotations(verdict: ChairVerdict) -> None:
    errors = [f for f in verdict.accepted_blockers if f.severity in {"CRITICAL", "HIGH"}]
    warns = [f for f in verdict.accepted_blockers + verdict.warnings if f.severity == "MEDIUM"]

    omitted_errors = max(0, len(errors) - MAX_ERRORS)
    omitted_warns = max(0, len(warns) - MAX_WARNINGS)

    for f in errors[:MAX_ERRORS]:
        line = f",line={f.line_start}" if f.line_start else ""
        desc = _sanitize_annotation_message(f.description)
        print(f"::error file={f.file}{line},title=Council {f.severity}::{desc}", file=sys.stderr)

    for f in warns[:MAX_WARNINGS]:
        line = f",line={f.line_start}" if f.line_start else ""
        desc = _sanitize_annotation_message(f.description)
        print(f"::warning file={f.file}{line},title=Council {f.severity}::{desc}", file=sys.stderr)

    if omitted_errors or omitted_warns:
        print(
            f"::warning title=Council annotations capped::Omitted {omitted_errors} errors and {omitted_warns} warnings due to cap. See council-report.json artifact for full findings.",
            file=sys.stderr,
        )


def _extract_pr_number(event_path: str) -> int | None:
    try:
        data = json.loads(open(event_path, encoding="utf-8").read())
    except Exception:
        return None
    pr = data.get("pull_request") or {}
    return pr.get("number")


def post_github_pr_review(verdict: ChairVerdict, reviewer_outputs: list[ReviewerOutput] | None = None) -> bool:
    """Emit annotations and best-effort sticky PR comment."""
    _emit_annotations(verdict)

    repo = os.getenv("GITHUB_REPOSITORY")
    token = os.getenv("GITHUB_TOKEN")
    event_path = os.getenv("GITHUB_EVENT_PATH")
    api_url = os.getenv("GITHUB_API_URL", "https://api.github.com")

    if not repo or not token or not event_path:
        return False

    pr_number = _extract_pr_number(event_path)
    if not pr_number:
        return False

    body = _build_comment_body(verdict, reviewer_outputs)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "code-review-council",
        "Content-Type": "application/json",
    }

    try:
        list_url = f"{api_url}/repos/{repo}/issues/{pr_number}/comments"
        req = request.Request(list_url, headers=headers, method="GET")
        with request.urlopen(req, timeout=10) as resp:
            comments = json.loads(resp.read().decode("utf-8"))

        existing_id = None
        for c in comments:
            if MARKER in c.get("body", ""):
                existing_id = c.get("id")
                break

        payload = json.dumps({"body": body}).encode("utf-8")
        if existing_id:
            url = f"{api_url}/repos/{repo}/issues/comments/{existing_id}"
            method = "PATCH"
        else:
            url = list_url
            method = "POST"

        req = request.Request(url, data=payload, headers=headers, method=method)
        with request.urlopen(req, timeout=10):
            return True
    except (error.URLError, error.HTTPError, TimeoutError, ValueError):
        return False

"""GitHub PR reporter — posts review findings as PR comments and workflow annotations."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from ..schemas import ChairFinding, ChairVerdict, ReviewerOutput

logger = logging.getLogger(__name__)

# Hidden marker to find/update existing comments instead of creating duplicates
_COMMENT_MARKER = "<!-- council-review-verdict -->"

# Annotation caps to avoid PR noise on large diffs
_MAX_ERRORS = 10
_MAX_WARNINGS = 10


def _get_pr_number() -> int | None:
    """Extract PR number from GitHub Actions environment."""
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not Path(event_path).exists():
        return None
    try:
        with open(event_path) as f:
            event = json.load(f)
        return event.get("pull_request", {}).get("number")
    except Exception:
        return None


def _github_api(
    method: str,
    endpoint: str,
    body: dict | None = None,
    token: str | None = None,
) -> dict | list | None:
    """Make a GitHub API request. Returns parsed JSON or None on failure."""
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    url = f"{api_url}{endpoint}"
    token = token or os.environ.get("GITHUB_TOKEN", "")

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, headers=headers, method=method)

    try:
        with urlopen(req) as resp:
            return json.loads(resp.read())
    except (HTTPError, URLError, json.JSONDecodeError) as e:
        logger.warning("GitHub API %s %s failed: %s", method, endpoint, e)
        return None


def _build_comment_body(
    verdict: ChairVerdict,
    reviewer_outputs: list[ReviewerOutput] | None = None,
) -> str:
    """Build the sticky PR comment body in markdown."""
    icon = {"PASS": "white_check_mark", "PASS_WITH_WARNINGS": "warning", "FAIL": "x"}
    verdict_icon = icon.get(verdict.verdict, "question")

    lines = [
        _COMMENT_MARKER,
        f"## :{verdict_icon}: Code Review Council — **{verdict.verdict}**",
        "",
        f"> {verdict.summary}",
        "",
    ]

    if verdict.degraded:
        lines.append("### Integrity Issues")
        for reason in verdict.degraded_reasons:
            lines.append(f"- {reason}")
        lines.append("")

    if verdict.accepted_blockers:
        lines.append("### Accepted Blockers")
        for f in verdict.accepted_blockers:
            loc = f"{f.file}:{f.line_start}" if f.line_start else f.file
            lines.append(f"- **[{f.severity}]** `{loc}` — {f.description}")
            if f.suggestion:
                lines.append(f"  - Suggestion: {f.suggestion}")
        lines.append("")

    if verdict.warnings:
        lines.append("### Warnings")
        for f in verdict.warnings:
            loc = f"{f.file}:{f.line_start}" if f.line_start else f.file
            lines.append(f"- **[{f.severity}]** `{loc}` — {f.description}")
        lines.append("")

    if reviewer_outputs:
        lines.append("### Reviewer Panel")
        lines.append("| Reviewer | Verdict | Findings | Confidence | Status |")
        lines.append("|----------|---------|----------|------------|--------|")
        for r in reviewer_outputs:
            status = f"error: {r.error[:50]}" if r.error else "ok"
            lines.append(
                f"| {r.reviewer_id} | {r.verdict} | {len(r.findings)} | "
                f"{r.confidence:.0%} | {status} |"
            )
        lines.append("")

    lines.append(f"*Confidence: {verdict.confidence:.0%} | "
                 f"Agreement: {verdict.reviewer_agreement_score:.0%}*")

    return "\n".join(lines)


def _emit_annotations(verdict: ChairVerdict) -> None:
    """Emit GitHub Actions workflow annotations for findings."""
    error_count = 0
    warning_count = 0

    all_findings: list[ChairFinding] = (
        verdict.accepted_blockers + verdict.warnings
    )

    for f in all_findings:
        if f.severity in ("CRITICAL", "HIGH"):
            if error_count >= _MAX_ERRORS:
                continue
            level = "error"
            error_count += 1
        elif f.severity == "MEDIUM":
            if warning_count >= _MAX_WARNINGS:
                continue
            level = "warning"
            warning_count += 1
        else:
            continue  # LOW severity suppressed

        file_part = f"file={f.file}" if f.file else ""
        line_part = f",line={f.line_start}" if f.line_start else ""
        msg = f"[{f.severity}] {f.description}"
        if f.suggestion:
            msg += f" — {f.suggestion}"

        print(f"::{level} {file_part}{line_part}::{msg}", file=sys.stderr)

    overflow = (
        max(0, sum(1 for f in all_findings if f.severity in ("CRITICAL", "HIGH")) - _MAX_ERRORS)
        + max(0, sum(1 for f in all_findings if f.severity == "MEDIUM") - _MAX_WARNINGS)
    )
    if overflow > 0:
        print(
            f"::warning ::Code Review Council: {overflow} additional finding(s) omitted from annotations. See PR comment for full details.",
            file=sys.stderr,
        )


def post_github_pr_review(
    verdict: ChairVerdict,
    reviewer_outputs: list[ReviewerOutput] | None = None,
) -> bool:
    """Post review results to a GitHub PR. Returns True if comment was posted.

    This function is best-effort: if any step fails (missing token, API error,
    fork PR restrictions), it logs a warning and returns False.
    Workflow annotations are always emitted regardless of API success.
    """
    # Always emit workflow annotations (works without API access)
    _emit_annotations(verdict)

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    pr_number = _get_pr_number()

    if not repo or not token or not pr_number:
        logger.warning(
            "GitHub PR reporter: missing GITHUB_REPOSITORY (%s), GITHUB_TOKEN (%s), "
            "or PR number (%s) — skipping PR comment",
            bool(repo), bool(token), pr_number,
        )
        return False

    comment_body = _build_comment_body(verdict, reviewer_outputs)

    # Try to find and update existing comment (sticky comment pattern)
    existing_comments = _github_api(
        "GET", f"/repos/{repo}/issues/{pr_number}/comments"
    )

    if isinstance(existing_comments, list):
        for comment in existing_comments:
            if isinstance(comment, dict) and _COMMENT_MARKER in comment.get("body", ""):
                # Update existing comment
                result = _github_api(
                    "PATCH",
                    f"/repos/{repo}/issues/comments/{comment['id']}",
                    body={"body": comment_body},
                    token=token,
                )
                if result:
                    logger.info("Updated existing PR comment #%s", comment["id"])
                    return True

    # No existing comment found — create new
    result = _github_api(
        "POST",
        f"/repos/{repo}/issues/{pr_number}/comments",
        body={"body": comment_body},
        token=token,
    )
    if result:
        logger.info("Created new PR comment")
        return True

    logger.warning("Failed to post PR comment")
    return False

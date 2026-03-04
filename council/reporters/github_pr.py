"""GitHub PR reporter: sticky comment + workflow annotations."""

from __future__ import annotations

import json
import os
import sys
import time
from urllib import error, request

from ..schemas import ChairVerdict, ReviewerOutput

MARKER = "<!-- council-review-verdict -->"
MAX_ERRORS = 10
MAX_WARNINGS = 10
DEFAULT_HTTP_TIMEOUT_SECONDS = 10
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 8.0


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
        with open(event_path, encoding="utf-8") as fh:
            data = json.loads(fh.read())
    except (OSError, ValueError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    pr = data.get("pull_request") or {}
    if not isinstance(pr, dict):
        return None

    number = pr.get("number")
    if isinstance(number, bool):
        return None
    if isinstance(number, int):
        return number if number > 0 else None
    if isinstance(number, str) and number.isdigit():
        parsed = int(number)
        return parsed if parsed > 0 else None
    return None


def _parse_comments_payload(payload: bytes) -> list[dict]:
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, TypeError):
        return []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _retry_after_seconds(exc: error.HTTPError) -> float | None:
    header = exc.headers.get("Retry-After") if exc.headers else None
    if not header:
        return None
    try:
        retry = float(header)
    except ValueError:
        return None
    return max(0.0, min(retry, MAX_BACKOFF_SECONDS))


def _request_with_retry(req: request.Request, timeout: float, max_retries: int, backoff_seconds: float):
    for attempt in range(max_retries + 1):
        try:
            return request.urlopen(req, timeout=timeout)
        except error.HTTPError as exc:
            should_retry = exc.code in {403, 429, 500, 502, 503, 504} and attempt < max_retries
            if not should_retry:
                raise

            wait_s = _retry_after_seconds(exc)
            if wait_s is None:
                wait_s = min(backoff_seconds * (2**attempt), MAX_BACKOFF_SECONDS)
            time.sleep(wait_s)
        except (error.URLError, TimeoutError):
            if attempt >= max_retries:
                raise
            wait_s = min(backoff_seconds * (2**attempt), MAX_BACKOFF_SECONDS)
            time.sleep(wait_s)

    raise RuntimeError("request retries exhausted")


def _read_float_env(name: str, default: float, minimum: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = float(raw)
    except ValueError:
        return default
    return max(minimum, parsed)


def _read_int_env(name: str, default: int, minimum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return max(minimum, parsed)


def post_github_pr_review(verdict: ChairVerdict, reviewer_outputs: list[ReviewerOutput] | None = None) -> bool:
    """Emit annotations and best-effort sticky PR comment."""
    _emit_annotations(verdict)

    repo = os.getenv("GITHUB_REPOSITORY")
    token = os.getenv("GITHUB_TOKEN")
    event_path = os.getenv("GITHUB_EVENT_PATH")
    api_url = os.getenv("GITHUB_API_URL", "https://api.github.com")
    http_timeout = _read_float_env("COUNCIL_GITHUB_HTTP_TIMEOUT", DEFAULT_HTTP_TIMEOUT_SECONDS, minimum=1.0)
    max_retries = _read_int_env("COUNCIL_GITHUB_MAX_RETRIES", DEFAULT_MAX_RETRIES, minimum=0)
    backoff_seconds = _read_float_env("COUNCIL_GITHUB_RETRY_BACKOFF_SECONDS", DEFAULT_BACKOFF_SECONDS, minimum=0.0)

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
        with _request_with_retry(req, timeout=http_timeout, max_retries=max_retries, backoff_seconds=backoff_seconds) as resp:
            comments = _parse_comments_payload(resp.read())

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
        with _request_with_retry(req, timeout=http_timeout, max_retries=max_retries, backoff_seconds=backoff_seconds):
            return True
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, OSError):
        return False

"""GitHub PR reporter: sticky summary, workflow annotations, and inline comments."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import urlparse
from urllib import error, request

from .transport import reviewer_output_mode, transport_notes
from ..schemas import ChairFinding, ChairVerdict, ReviewerOutput

_MAX_EVENT_FILE_BYTES = 1_000_000  # 1 MB ceiling — GitHub event payloads are small

MARKER = "<!-- council-review-verdict -->"
INLINE_MARKER_PREFIX = "<!-- council-inline:"
INLINE_MARKER_RE = re.compile(r"<!-- council-inline:([0-9a-f]+) -->")
MAX_ERRORS = 10
MAX_WARNINGS = 10
DEFAULT_HTTP_TIMEOUT_SECONDS = 10
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 8.0
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _sanitize_annotation_message(message: str) -> str:
    """Sanitize message text for GitHub workflow command format."""
    return message.replace("\r", " ").replace("\n", " ").replace("::", ";;")


def _sanitize_comment_text(text: str | None, *, max_len: int = 400) -> str:
    """Normalize untrusted text before embedding it in markdown comments."""
    cleaned = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _CONTROL_CHARS_RE.sub("", cleaned)
    cleaned = " ".join(part for part in cleaned.split())
    cleaned = cleaned.replace("`", "'")
    cleaned = cleaned.replace("<", "&lt;").replace(">", "&gt;")
    cleaned = cleaned.replace("[", r"\[").replace("]", r"\]")
    cleaned = cleaned.replace("|", r"\|")
    cleaned = cleaned.strip()
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1].rstrip() + "…"
    return cleaned


def _normalize_inline_key_text(text: str | None) -> str:
    return " ".join((text or "").split()).strip().lower()


def _inline_key(finding: ChairFinding) -> str:
    """Return a stable dedupe key for an accepted finding."""
    payload = "|".join(
        [
            finding.file,
            str(finding.line_start or ""),
            str(finding.line_end or ""),
            _normalize_inline_key_text(finding.symbol_name),
            _normalize_inline_key_text(finding.description),
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _build_inline_comment_body(finding: ChairFinding, key: str) -> str:
    """Build a concise inline review comment body."""
    location = finding.file
    if finding.line_start:
        location += f":{finding.line_start}"

    lines = [
        f"{INLINE_MARKER_PREFIX}{key} -->",
        f"**Council {finding.severity} [{finding.category}]** at `{location}`",
        "",
        _sanitize_comment_text(finding.description, max_len=500),
    ]
    if finding.suggestion:
        lines.extend(["", f"Suggested fix: {_sanitize_comment_text(finding.suggestion, max_len=400)}"])
    if finding.source_reviewers:
        lines.extend(["", f"Source: {', '.join(finding.source_reviewers)}"])
    return "\n".join(lines)


def _build_comment_body(
    verdict: ChairVerdict,
    reviewer_outputs: list[ReviewerOutput] | None = None,
) -> str:
    lines = [
        MARKER,
        "## Code Review Council",
        f"**Overall verdict:** `{verdict.verdict}` (confidence: {verdict.confidence:.2f})",
        "",
        f"Model-generated summary: {_sanitize_comment_text(verdict.summary, max_len=600)}",
    ]

    notes = transport_notes(verdict, reviewer_outputs)
    if notes:
        lines.extend(["", "### Transport notes"])
        for note in notes:
            lines.append(f"- {note}")

    if verdict.degraded and verdict.degraded_reasons:
        lines.extend(["", "### Degraded integrity signals"])
        for reason in verdict.degraded_reasons:
            lines.append(f"- {_sanitize_comment_text(reason, max_len=300)}")

    if verdict.accepted_blockers:
        lines.extend(["", "### Accepted blockers"])
        for finding in verdict.accepted_blockers:
            loc = f"`{finding.file}:{finding.line_start}`" if finding.line_start else f"`{finding.file}`"
            suggestion = (
                f" - _Suggestion_: {_sanitize_comment_text(finding.suggestion, max_len=250)}"
                if finding.suggestion
                else ""
            )
            lines.append(
                f"- **[{finding.severity}]** {loc} "
                f"{_sanitize_comment_text(finding.description, max_len=350)}{suggestion}"
            )

    if verdict.warnings:
        lines.extend(["", "### Accepted warnings"])
        for finding in verdict.warnings:
            loc = f"`{finding.file}:{finding.line_start}`" if finding.line_start else f"`{finding.file}`"
            suggestion = (
                f" - _Suggestion_: {_sanitize_comment_text(finding.suggestion, max_len=250)}"
                if finding.suggestion
                else ""
            )
            lines.append(
                f"- **[{finding.severity}]** {loc} "
                f"{_sanitize_comment_text(finding.description, max_len=350)}{suggestion}"
            )

    if reviewer_outputs:
        lines.extend(
            [
                "",
                "### Reviewer panel",
                "| Reviewer | Verdict | Findings | Output mode | Error |",
                "|---|---:|---:|---|---|",
            ]
        )
        for reviewer in reviewer_outputs:
            lines.append(
                f"| `{reviewer.reviewer_id}` | {reviewer.verdict} | {len(reviewer.findings)} | "
                f"{reviewer_output_mode(reviewer)} | {_sanitize_comment_text(reviewer.error or '', max_len=160)} |"
            )

    return "\n".join(lines) + "\n"


def _emit_annotations(verdict: ChairVerdict) -> None:
    errors = [finding for finding in verdict.accepted_blockers if finding.severity in {"CRITICAL", "HIGH"}]
    warns = [finding for finding in verdict.accepted_blockers + verdict.warnings if finding.severity == "MEDIUM"]

    omitted_errors = max(0, len(errors) - MAX_ERRORS)
    omitted_warns = max(0, len(warns) - MAX_WARNINGS)

    for finding in errors[:MAX_ERRORS]:
        line = f",line={finding.line_start}" if finding.line_start else ""
        desc = _sanitize_annotation_message(finding.description)
        print(f"::error file={finding.file}{line},title=Council {finding.severity}::{desc}", file=sys.stderr)

    for finding in warns[:MAX_WARNINGS]:
        line = f",line={finding.line_start}" if finding.line_start else ""
        desc = _sanitize_annotation_message(finding.description)
        print(f"::warning file={finding.file}{line},title=Council {finding.severity}::{desc}", file=sys.stderr)

    if omitted_errors or omitted_warns:
        print(
            f"::warning title=Council annotations capped::Omitted {omitted_errors} errors and {omitted_warns} warnings due to cap. See council-report.json artifact for full findings.",
            file=sys.stderr,
        )


def _safe_read_event_file(path: str) -> dict | None:
    """Read a GitHub event JSON file, rejecting non-files and oversized inputs."""
    if not path:
        return None
    from pathlib import Path
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        return None
    try:
        if p.stat().st_size > _MAX_EVENT_FILE_BYTES:
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _extract_pr_context(event_path: str) -> tuple[int | None, str | None]:
    data = _safe_read_event_file(event_path)
    if data is None:
        return None, None

    pr = data.get("pull_request") or {}
    if not isinstance(pr, dict):
        return None, None

    number = pr.get("number")
    pr_number: int | None = None
    if isinstance(number, bool):
        pr_number = None
    elif isinstance(number, int) and number > 0:
        pr_number = number
    elif isinstance(number, str) and number.isdigit():
        parsed = int(number)
        pr_number = parsed if parsed > 0 else None

    head = pr.get("head") or {}
    head_sha = head.get("sha") if isinstance(head, dict) else None
    return pr_number, head_sha if isinstance(head_sha, str) and head_sha else None


def _extract_pr_number(event_path: str) -> int | None:
    """Backward-compatible helper returning only the PR number."""
    pr_number, _ = _extract_pr_context(event_path)
    return pr_number


def _extract_pr_head_sha(event_path: str) -> str | None:
    """Return the PR head sha from the GitHub event payload."""
    _, head_sha = _extract_pr_context(event_path)
    return head_sha


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


def _resolve_github_api_url(raw_url: str | None) -> str:
    """Return a strictly validated GitHub API base URL.

    Accepts the public GitHub API default and strict GitHub Enterprise-style
    `https://host/api/v3` URLs. Anything else falls back to the public default.
    """
    default_url = "https://api.github.com"
    if not raw_url:
        return default_url

    parsed = urlparse(raw_url.strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        return default_url

    path = parsed.path.rstrip("/")
    if parsed.hostname.lower() == "api.github.com" and path in {"", "/"}:
        return default_url

    if path != "/api/v3":
        return default_url

    netloc = parsed.hostname
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return f"https://{netloc}/api/v3"


def _build_inline_comment_candidates(verdict: ChairVerdict) -> list[dict]:
    """Return deduped inline comment payloads for accepted findings with file/line info."""
    candidates: list[dict] = []
    seen_keys: set[str] = set()

    for finding in verdict.accepted_blockers + verdict.warnings:
        if not finding.file or not finding.line_start:
            continue

        key = _inline_key(finding)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        payload = {
            "key": key,
            "path": finding.file,
            "line": finding.line_end or finding.line_start,
            "side": "RIGHT",
            "body": _build_inline_comment_body(finding, key),
        }
        if finding.line_end and finding.line_end > finding.line_start:
            payload["start_line"] = finding.line_start
            payload["start_side"] = "RIGHT"

        candidates.append(payload)

    return candidates


def _existing_inline_keys(
    repo: str,
    pr_number: int,
    headers: dict[str, str],
    api_url: str,
    timeout: float,
    max_retries: int,
    backoff_seconds: float,
) -> set[str]:
    url = f"{api_url}/repos/{repo}/pulls/{pr_number}/comments?per_page=100"
    req = request.Request(url, headers=headers, method="GET")
    with _request_with_retry(req, timeout=timeout, max_retries=max_retries, backoff_seconds=backoff_seconds) as resp:
        comments = _parse_comments_payload(resp.read())

    keys: set[str] = set()
    for comment in comments:
        body = comment.get("body", "")
        if not isinstance(body, str):
            continue
        match = INLINE_MARKER_RE.search(body)
        if match:
            keys.add(match.group(1))
    return keys


def _post_inline_comments(
    verdict: ChairVerdict,
    repo: str,
    pr_number: int,
    head_sha: str | None,
    headers: dict[str, str],
    api_url: str,
    timeout: float,
    max_retries: int,
    backoff_seconds: float,
) -> bool:
    if not head_sha:
        return False

    candidates = _build_inline_comment_candidates(verdict)
    if not candidates:
        return False

    try:
        existing_keys = _existing_inline_keys(
            repo=repo,
            pr_number=pr_number,
            headers=headers,
            api_url=api_url,
            timeout=timeout,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
        )
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, OSError):
        existing_keys = set()

    any_posted = False
    url = f"{api_url}/repos/{repo}/pulls/{pr_number}/comments"
    for payload in candidates:
        if payload["key"] in existing_keys:
            continue

        comment_payload = {
            "body": payload["body"],
            "commit_id": head_sha,
            "path": payload["path"],
            "line": payload["line"],
            "side": payload["side"],
        }
        if "start_line" in payload:
            comment_payload["start_line"] = payload["start_line"]
            comment_payload["start_side"] = payload["start_side"]

        req = request.Request(
            url,
            data=json.dumps(comment_payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with _request_with_retry(req, timeout=timeout, max_retries=max_retries, backoff_seconds=backoff_seconds):
                any_posted = True
        except (error.URLError, error.HTTPError, TimeoutError, ValueError, OSError):
            continue

    return any_posted


def post_github_pr_review(
    verdict: ChairVerdict,
    reviewer_outputs: list[ReviewerOutput] | None = None,
) -> bool:
    """Emit annotations and best-effort GitHub PR reporting."""
    _emit_annotations(verdict)

    repo = os.getenv("GITHUB_REPOSITORY")
    token = os.getenv("GITHUB_TOKEN")
    event_path = os.getenv("GITHUB_EVENT_PATH")
    api_url = _resolve_github_api_url(os.getenv("GITHUB_API_URL"))
    http_timeout = _read_float_env("COUNCIL_GITHUB_HTTP_TIMEOUT", DEFAULT_HTTP_TIMEOUT_SECONDS, minimum=1.0)
    max_retries = _read_int_env("COUNCIL_GITHUB_MAX_RETRIES", DEFAULT_MAX_RETRIES, minimum=0)
    backoff_seconds = _read_float_env("COUNCIL_GITHUB_RETRY_BACKOFF_SECONDS", DEFAULT_BACKOFF_SECONDS, minimum=0.0)

    if not repo or not token or not event_path:
        return False

    pr_number = _extract_pr_number(event_path)
    head_sha = _extract_pr_head_sha(event_path)
    if not pr_number:
        return False

    body = _build_comment_body(verdict, reviewer_outputs)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "code-review-council",
        "Content-Type": "application/json",
    }

    sticky_posted = False
    try:
        list_url = f"{api_url}/repos/{repo}/issues/{pr_number}/comments"
        req = request.Request(list_url, headers=headers, method="GET")
        with _request_with_retry(req, timeout=http_timeout, max_retries=max_retries, backoff_seconds=backoff_seconds) as resp:
            comments = _parse_comments_payload(resp.read())

        existing_id = None
        for comment in comments:
            if MARKER in comment.get("body", ""):
                existing_id = comment.get("id")
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
            sticky_posted = True
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, OSError):
        sticky_posted = False

    inline_posted = _post_inline_comments(
        verdict=verdict,
        repo=repo,
        pr_number=pr_number,
        head_sha=head_sha,
        headers=headers,
        api_url=api_url,
        timeout=http_timeout,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
    )

    return sticky_posted or inline_posted

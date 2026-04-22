"""Local, privacy-preserving review history storage."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .schemas import ChairFinding, ChairVerdict, GateZeroResult, ReviewerOutput, ReviewPack

SCHEMA_VERSION = 1
_GIT_TIMEOUT_SECONDS = 5.0


class HistorySchemaError(RuntimeError):
    """Raised when the on-disk history schema is incompatible."""


class HistoryPathError(ValueError):
    """Raised when a configured history path escapes the repository boundary."""


@dataclass(slots=True)
class RepeatFindingSummary:
    """Aggregated repeated-fingerprint row for the summary command."""

    fingerprint: str
    severity: str
    category: str
    file_path: str
    reviewer_id: str
    policy_id: str | None
    run_count: int
    consecutive_count: int
    is_debt: bool


@dataclass(slots=True)
class HistorySummary:
    """Local review-history summary for one repository."""

    repo_display: str
    db_path: Path
    days: int
    total_runs: int
    degraded_runs: int
    verdict_counts: dict[str, int]
    severity_counts: dict[str, int]
    category_counts: dict[str, int]
    repeats: list[RepeatFindingSummary]


@dataclass(slots=True)
class HistoryHealth:
    """Non-blocking doctor status for history storage."""

    status: str
    detail: str
    remediation: str | None = None


_MIGRATION_1 = (
    """
    CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY,
        repo_id TEXT NOT NULL,
        repo_display TEXT NOT NULL,
        created_at TEXT NOT NULL,
        branch TEXT,
        diff_target TEXT,
        commit_sha TEXT,
        ci_mode INTEGER NOT NULL,
        audience TEXT NOT NULL,
        verdict TEXT NOT NULL,
        confidence REAL NOT NULL,
        degraded INTEGER NOT NULL,
        degraded_reasons_json TEXT NOT NULL,
        files_changed INTEGER NOT NULL,
        lines_changed INTEGER NOT NULL,
        token_estimate INTEGER NOT NULL,
        languages_json TEXT NOT NULL,
        reviewer_models_json TEXT NOT NULL,
        output_modes_json TEXT NOT NULL,
        accepted_blockers_count INTEGER NOT NULL,
        warnings_count INTEGER NOT NULL,
        dismissed_count INTEGER NOT NULL,
        total_findings_count INTEGER NOT NULL,
        severity_counts_json TEXT NOT NULL,
        category_counts_json TEXT NOT NULL,
        duration_ms INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS findings (
        run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        fingerprint TEXT NOT NULL,
        severity TEXT NOT NULL,
        category TEXT NOT NULL,
        file_path TEXT NOT NULL,
        reviewer_id TEXT NOT NULL,
        policy_id TEXT,
        verdict TEXT NOT NULL,
        is_repeated INTEGER NOT NULL,
        debt_run_count INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_runs_repo_created ON runs(repo_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_findings_fingerprint ON findings(fingerprint)",
)

_MIGRATIONS: dict[int, tuple[str, ...]] = {1: _MIGRATION_1}


def resolve_history_path(config_path: str = "", repo_root: Path | None = None) -> Path:
    """Resolve the configured SQLite path, defaulting to the OS user cache."""
    raw_path = (config_path or "").strip()
    if raw_path:
        path = Path(raw_path)
        if path.is_absolute() or str(path).startswith("~"):
            raise HistoryPathError(
                "[history].path must be a relative path inside the repository"
            )
        base = (repo_root or Path.cwd()).resolve()
        resolved = (base / path).resolve()
        try:
            resolved.relative_to(base)
        except ValueError as exc:
            raise HistoryPathError(
                "[history].path must not traverse outside the repository"
            ) from exc
        return resolved

    return (_default_cache_dir() / "code-review-council" / "history.sqlite").resolve()


def repository_identity(repo_root: Path) -> tuple[str, str]:
    """Return a stable repository id and human-readable display name."""
    root = repo_root.resolve()
    normalized = os.path.normcase(str(root))
    repo_id = hashlib.sha256(normalized.encode("utf-8", errors="surrogateescape")).hexdigest()
    return repo_id, root.name or str(root)


def connect_history_db(path: Path) -> sqlite3.Connection:
    """Open the history database and enable foreign-key enforcement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def current_schema_version(conn: sqlite3.Connection) -> int:
    """Return the highest applied schema version, or 0 for an empty database."""
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = '_schema_migrations'"
    ).fetchone()
    if table_exists is None:
        return 0
    row = conn.execute("SELECT MAX(version) AS version FROM _schema_migrations").fetchone()
    return int(row["version"] or 0)


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Apply forward-only idempotent migrations up to the current schema version."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    version = current_schema_version(conn)
    if version > SCHEMA_VERSION:
        raise HistorySchemaError(
            f"history schema v{version} is newer than this council runtime supports (v{SCHEMA_VERSION})"
        )

    with conn:
        for migration_version in range(version + 1, SCHEMA_VERSION + 1):
            for statement in _MIGRATIONS[migration_version]:
                conn.execute(statement)
            conn.execute(
                "INSERT OR IGNORE INTO _schema_migrations(version, applied_at) VALUES (?, ?)",
                (migration_version, _utcnow_iso()),
            )


def fingerprint_for_finding(finding: ChairFinding) -> str:
    """Return a stable fingerprint without storing model-generated text."""
    description_hash = hashlib.sha256(
        _normalize_text(finding.description).encode("utf-8", errors="surrogateescape")
    ).hexdigest()
    parts = [
        finding.severity.upper(),
        finding.category.lower(),
        _normalize_path(finding.file),
        _normalize_text(finding.symbol_name or ""),
        _normalize_text(finding.policy_id or ""),
        description_hash,
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def record_review_history(
    *,
    repo_root: Path,
    config: Any,
    verdict: ChairVerdict,
    review_pack: ReviewPack | None,
    reviewer_outputs: list[ReviewerOutput],
    gate_result: GateZeroResult | None,
    ci_mode: bool,
    staged: bool,
    branch: str | None,
    audience: str,
    output_modes: list[str],
    duration_ms: int,
) -> Path:
    """Persist one review run using the configured best-effort history store."""
    history_config = config.history
    db_path = resolve_history_path(history_config.path, repo_root)
    repo_id, repo_display = repository_identity(repo_root)
    created_at = _utcnow_iso()

    conn = connect_history_db(db_path)
    try:
        ensure_schema(conn)
        prune_history(conn, repo_id, int(history_config.retention_days))

        prior_sets = _prior_run_fingerprint_sets(conn, repo_id)
        finding_rows = _build_finding_rows(verdict, prior_sets)

        run_id = uuid.uuid4().hex
        severity_counts = _count_by(finding_rows, "severity")
        category_counts = _count_by(finding_rows, "category")
        run_metadata = _build_run_metadata(
            repo_root=repo_root,
            config=config,
            review_pack=review_pack,
            reviewer_outputs=reviewer_outputs,
            staged=staged,
            branch=branch,
        )

        with conn:
            conn.execute(
                """
                INSERT INTO runs (
                    id, repo_id, repo_display, created_at, branch, diff_target, commit_sha,
                    ci_mode, audience, verdict, confidence, degraded, degraded_reasons_json,
                    files_changed, lines_changed, token_estimate, languages_json,
                    reviewer_models_json, output_modes_json, accepted_blockers_count,
                    warnings_count, dismissed_count, total_findings_count,
                    severity_counts_json, category_counts_json, duration_ms
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    run_id,
                    repo_id,
                    repo_display,
                    created_at,
                    run_metadata["branch"],
                    run_metadata["diff_target"],
                    run_metadata["commit_sha"],
                    int(ci_mode),
                    audience,
                    verdict.verdict,
                    float(verdict.confidence),
                    int(verdict.degraded),
                    _json_dumps(verdict.degraded_reasons),
                    run_metadata["files_changed"],
                    run_metadata["lines_changed"],
                    run_metadata["token_estimate"],
                    _json_dumps(run_metadata["languages"]),
                    _json_dumps(run_metadata["reviewer_models"]),
                    _json_dumps(output_modes),
                    len(verdict.accepted_blockers),
                    len(verdict.warnings),
                    len(verdict.dismissed_findings),
                    len(finding_rows),
                    _json_dumps(severity_counts),
                    _json_dumps(category_counts),
                    max(0, int(duration_ms)),
                ),
            )
            conn.executemany(
                """
                INSERT INTO findings (
                    run_id, fingerprint, severity, category, file_path,
                    reviewer_id, policy_id, verdict, is_repeated, debt_run_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        row["fingerprint"],
                        row["severity"],
                        row["category"],
                        row["file_path"],
                        row["reviewer_id"],
                        row["policy_id"],
                        row["verdict"],
                        int(row["is_repeated"]),
                        row["debt_run_count"],
                    )
                    for row in finding_rows
                ],
            )
    finally:
        conn.close()

    return db_path


def prune_history(
    conn: sqlite3.Connection,
    repo_id: str,
    retention_days: int,
    now: datetime | None = None,
) -> int:
    """Delete run rows older than the retention window for this repository."""
    if retention_days <= 0:
        return 0
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    with conn:
        cursor = conn.execute(
            "DELETE FROM runs WHERE repo_id = ? AND created_at < ?",
            (repo_id, _format_utc(cutoff)),
        )
    return max(0, cursor.rowcount)


def summarize_history(
    *,
    repo_root: Path,
    history_config: Any,
    days: int = 30,
    limit: int = 10,
) -> HistorySummary:
    """Build a privacy-preserving summary for one repository."""
    db_path = resolve_history_path(history_config.path, repo_root)
    repo_id, repo_display = repository_identity(repo_root)
    since = _format_utc(datetime.now(UTC) - timedelta(days=max(1, days)))

    conn = connect_history_db(db_path)
    try:
        ensure_schema(conn)
        total_runs = _scalar_int(
            conn,
            "SELECT COUNT(*) FROM runs WHERE repo_id = ? AND created_at >= ?",
            (repo_id, since),
        )
        degraded_runs = _scalar_int(
            conn,
            "SELECT COUNT(*) FROM runs WHERE repo_id = ? AND created_at >= ? AND degraded = 1",
            (repo_id, since),
        )
        verdict_counts = _group_counts(
            conn,
            "SELECT verdict, COUNT(*) AS count FROM runs WHERE repo_id = ? AND created_at >= ? GROUP BY verdict",
            (repo_id, since),
            "verdict",
        )
        severity_counts = _group_counts(
            conn,
            """
            SELECT f.severity, COUNT(*) AS count
            FROM findings f
            JOIN runs r ON r.id = f.run_id
            WHERE r.repo_id = ? AND r.created_at >= ?
            GROUP BY f.severity
            """,
            (repo_id, since),
            "severity",
        )
        category_counts = _group_counts(
            conn,
            """
            SELECT f.category, COUNT(*) AS count
            FROM findings f
            JOIN runs r ON r.id = f.run_id
            WHERE r.repo_id = ? AND r.created_at >= ?
            GROUP BY f.category
            """,
            (repo_id, since),
            "category",
        )
        repeats = _repeat_summaries(conn, repo_id, since, max(1, limit))
    finally:
        conn.close()

    return HistorySummary(
        repo_display=repo_display,
        db_path=db_path,
        days=max(1, days),
        total_runs=total_runs,
        degraded_runs=degraded_runs,
        verdict_counts=verdict_counts,
        severity_counts=severity_counts,
        category_counts=category_counts,
        repeats=repeats,
    )


def format_history_summary(summary: HistorySummary) -> list[str]:
    """Render summary output for the terminal CLI."""
    if summary.total_runs == 0:
        return [
            f"Council history summary for {summary.repo_display}",
            f"No history recorded for this repo in the last {summary.days} day(s).",
            f"History database: {summary.db_path}",
        ]

    lines = [
        f"Council history summary for {summary.repo_display}",
        f"Runs: {summary.total_runs} in the last {summary.days} day(s)",
        f"Degraded runs: {summary.degraded_runs}",
        f"Verdicts: {_format_counts(summary.verdict_counts)}",
        f"Severity counts: {_format_counts(summary.severity_counts)}",
        f"Category counts: {_format_counts(summary.category_counts)}",
        "Repeated fingerprints:",
    ]
    if not summary.repeats:
        lines.append("  None seen in two or more runs.")
    for repeat in summary.repeats:
        marker = "[DEBT]" if repeat.is_debt else "[REPEAT]"
        policy = f", policy={repeat.policy_id}" if repeat.policy_id else ""
        lines.append(
            "  "
            f"{marker} {repeat.severity}/{repeat.category} {repeat.file_path} "
            f"fingerprint={repeat.fingerprint[:12]} "
            f"seen={repeat.run_count}, consecutive={repeat.consecutive_count}, "
            f"reviewer={repeat.reviewer_id}{policy}"
        )
    lines.append(f"History database: {summary.db_path}")
    return lines


def check_history_health(repo_root: Path, history_config: Any) -> HistoryHealth:
    """Validate history storage for doctor without affecting doctor exit codes."""
    if not history_config.enabled:
        return HistoryHealth("INFO", "History storage is disabled.")

    db_path: Path | None = None
    try:
        db_path = resolve_history_path(history_config.path, repo_root)
        repo_id, _repo_display = repository_identity(repo_root)
        conn = connect_history_db(db_path)
        try:
            ensure_schema(conn)
            version = current_schema_version(conn)
            if version != SCHEMA_VERSION:
                raise HistorySchemaError(
                    f"expected schema v{SCHEMA_VERSION}, found v{version}"
                )
            pruned = prune_history(conn, repo_id, int(history_config.retention_days))
            newest = conn.execute(
                "SELECT MAX(created_at) AS newest FROM runs WHERE repo_id = ?",
                (repo_id,),
            ).fetchone()["newest"]
        finally:
            conn.close()
    except (OSError, sqlite3.Error, HistoryPathError, HistorySchemaError) as exc:
        target = db_path if db_path is not None else "[history].path"
        return HistoryHealth(
            "WARN",
            f"History storage check failed for {target}: {exc}",
            "Use a repo-relative [history].path or remove an incompatible history database.",
        )

    stale_note = ""
    if newest:
        try:
            newest_dt = _parse_utc(newest)
            if newest_dt < datetime.now(UTC) - timedelta(days=30):
                stale_note = "; no run has been logged in the last 30 days"
        except ValueError:
            stale_note = "; newest run timestamp could not be parsed"
    else:
        stale_note = "; no runs recorded yet"

    prune_note = f"; pruned {pruned} expired run(s)" if pruned else "; retention pruning ok"
    return HistoryHealth(
        "INFO",
        f"History DB writable at {db_path}; schema v{version}{prune_note}{stale_note}.",
    )


def _default_cache_dir() -> Path:
    if os.name == "nt":
        return Path(os.getenv("LOCALAPPDATA") or (Path.home() / ".cache"))
    if sys_platform := os.getenv("XDG_CACHE_HOME"):
        return Path(sys_platform).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches"
    return Path.home() / ".cache"


def _build_run_metadata(
    *,
    repo_root: Path,
    config: Any,
    review_pack: ReviewPack | None,
    reviewer_outputs: list[ReviewerOutput],
    staged: bool,
    branch: str | None,
) -> dict[str, Any]:
    current_branch = _git_output(repo_root, "rev-parse", "--abbrev-ref", "HEAD") or ""
    commit_sha = _git_output(repo_root, "rev-parse", "HEAD") or ""
    diff_target = branch or ("staged" if staged else "")
    if not diff_target and review_pack is not None:
        diff_target = review_pack.branch or review_pack.commit_range

    files_changed = len(review_pack.changed_files) if review_pack else 0
    lines_changed = int(review_pack.total_lines_changed) if review_pack else 0
    token_estimate = int(review_pack.token_estimate) if review_pack else 0
    languages = sorted(set(review_pack.languages_detected)) if review_pack else []
    reviewer_models = {
        "chair": config.chair_model,
        "reviewers": {
            reviewer.id: reviewer.model for reviewer in getattr(config, "active_reviewers", [])
        },
        "outputs": {
            output.reviewer_id: output.model for output in reviewer_outputs
        },
    }
    return {
        "branch": current_branch,
        "diff_target": diff_target,
        "commit_sha": commit_sha,
        "files_changed": files_changed,
        "lines_changed": lines_changed,
        "token_estimate": token_estimate,
        "languages": languages,
        "reviewer_models": reviewer_models,
    }


def _build_finding_rows(
    verdict: ChairVerdict,
    prior_sets: list[set[str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for finding, finding_verdict in _iter_verdict_findings(verdict):
        fingerprint = fingerprint_for_finding(finding)
        prior_count = _prior_consecutive_count(fingerprint, prior_sets)
        debt_run_count = prior_count + 1
        rows.append(
            {
                "fingerprint": fingerprint,
                "severity": finding.severity,
                "category": finding.category,
                "file_path": _normalize_path(finding.file),
                "reviewer_id": _reviewer_id_for_finding(finding),
                "policy_id": finding.policy_id,
                "verdict": finding_verdict,
                "is_repeated": debt_run_count >= 2,
                "debt_run_count": debt_run_count,
            }
        )
    return rows


def _iter_verdict_findings(verdict: ChairVerdict) -> list[tuple[ChairFinding, str]]:
    rows: list[tuple[ChairFinding, str]] = []
    rows.extend((finding, "accepted_blocker") for finding in verdict.accepted_blockers)
    rows.extend((finding, "warning") for finding in verdict.warnings)
    rows.extend((finding, "dismissed") for finding in verdict.dismissed_findings)
    return rows


def _prior_run_fingerprint_sets(conn: sqlite3.Connection, repo_id: str) -> list[set[str]]:
    rows = conn.execute(
        """
        SELECT r.id AS run_id, f.fingerprint AS fingerprint
        FROM runs r
        LEFT JOIN findings f ON f.run_id = r.id
        WHERE r.repo_id = ?
        ORDER BY r.created_at DESC, r.id DESC
        """,
        (repo_id,),
    ).fetchall()

    fingerprint_sets: list[set[str]] = []
    current_run_id: str | None = None
    current_fingerprints: set[str] = set()
    for row in rows:
        run_id = row["run_id"]
        if run_id != current_run_id:
            if current_run_id is not None:
                fingerprint_sets.append(current_fingerprints)
            current_run_id = run_id
            current_fingerprints = set()
        if row["fingerprint"] is not None:
            current_fingerprints.add(row["fingerprint"])
    if current_run_id is not None:
        fingerprint_sets.append(current_fingerprints)
    return fingerprint_sets


def _prior_consecutive_count(fingerprint: str, prior_sets: list[set[str]]) -> int:
    count = 0
    for fingerprints in prior_sets:
        if fingerprint not in fingerprints:
            break
        count += 1
    return count


def _repeat_summaries(
    conn: sqlite3.Connection,
    repo_id: str,
    since: str,
    limit: int,
) -> list[RepeatFindingSummary]:
    repeat_rows = conn.execute(
        """
        SELECT f.fingerprint, COUNT(DISTINCT f.run_id) AS run_count, MAX(r.created_at) AS latest_seen
        FROM findings f
        JOIN runs r ON r.id = f.run_id
        WHERE r.repo_id = ? AND r.created_at >= ?
        GROUP BY f.fingerprint
        HAVING COUNT(DISTINCT f.run_id) >= 2
        ORDER BY run_count DESC, latest_seen DESC
        LIMIT ?
        """,
        (repo_id, since, limit),
    ).fetchall()

    summaries: list[RepeatFindingSummary] = []
    for repeat in repeat_rows:
        metadata = conn.execute(
            """
            SELECT f.severity, f.category, f.file_path, f.reviewer_id, f.policy_id
            FROM findings f
            JOIN runs r ON r.id = f.run_id
            WHERE r.repo_id = ? AND f.fingerprint = ?
            ORDER BY r.created_at DESC, f.rowid DESC
            LIMIT 1
            """,
            (repo_id, repeat["fingerprint"]),
        ).fetchone()
        if metadata is None:
            continue
        consecutive_count = _current_consecutive_count(conn, repo_id, repeat["fingerprint"])
        summaries.append(
            RepeatFindingSummary(
                fingerprint=repeat["fingerprint"],
                severity=metadata["severity"],
                category=metadata["category"],
                file_path=metadata["file_path"],
                reviewer_id=metadata["reviewer_id"],
                policy_id=metadata["policy_id"],
                run_count=int(repeat["run_count"]),
                consecutive_count=consecutive_count,
                is_debt=consecutive_count >= 3,
            )
        )
    return summaries


def _current_consecutive_count(conn: sqlite3.Connection, repo_id: str, fingerprint: str) -> int:
    # TODO: replace this per-fingerprint scan with a window-function query once
    # local history volumes grow beyond the first-slice SQLite use case.
    runs = conn.execute(
        "SELECT id FROM runs WHERE repo_id = ? ORDER BY created_at DESC, id DESC",
        (repo_id,),
    ).fetchall()
    count = 0
    for run in runs:
        present = conn.execute(
            "SELECT 1 FROM findings WHERE run_id = ? AND fingerprint = ? LIMIT 1",
            (run["id"], fingerprint),
        ).fetchone()
        if present is None:
            break
        count += 1
    return count


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row[key])
        counts[value] = counts.get(value, 0) + 1
    return counts


def _group_counts(
    conn: sqlite3.Connection,
    query: str,
    params: tuple[Any, ...],
    key: str,
) -> dict[str, int]:
    return {str(row[key]): int(row["count"]) for row in conn.execute(query, params).fetchall()}


def _scalar_int(conn: sqlite3.Connection, query: str, params: tuple[Any, ...]) -> int:
    row = conn.execute(query, params).fetchone()
    return int(row[0] or 0)


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}={counts[key]}" for key in sorted(counts))


def _reviewer_id_for_finding(finding: ChairFinding) -> str:
    reviewers = [reviewer for reviewer in finding.source_reviewers if reviewer]
    return ",".join(sorted(set(reviewers))) or "chair"


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _git_output(repo_root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _utcnow_iso() -> str:
    return _format_utc(datetime.now(UTC))


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)

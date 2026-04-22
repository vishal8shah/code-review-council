from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from council.config import CouncilConfig, HistoryConfig, ReviewerConfig
from council.history import (
    SCHEMA_VERSION,
    HistorySchemaError,
    check_history_health,
    connect_history_db,
    current_schema_version,
    ensure_schema,
    format_history_summary,
    prune_history,
    record_review_history,
    resolve_history_path,
    summarize_history,
)
from council.schemas import ChairFinding, ChairVerdict, ReviewerOutput, ReviewPack


def _config(db_path, retention_days: int = 180) -> CouncilConfig:
    return CouncilConfig(
        chair_model="gemini/gemini-3-pro-preview",
        history=HistoryConfig(
            enabled=True,
            path=str(db_path),
            retention_days=retention_days,
            store_finding_text=False,
        ),
        reviewers=[
            ReviewerConfig(
                id="secops",
                name="SecOps",
                model="gemini/gemini-3-pro-preview",
                enabled=True,
            )
        ],
    )


def _review_pack(secret: str = "raw diff must not be stored") -> ReviewPack:
    return ReviewPack(
        diff_text=f"diff --git a/src/app.py b/src/app.py\n+{secret}",
        changed_files=["src/app.py"],
        languages_detected=["python"],
        total_lines_changed=4,
        token_estimate=128,
        branch="main",
    )


def _verdict(
    *,
    description: str = "repeatable unsafe auth check",
    file_path: str = "src/app.py",
    verdict: str = "FAIL",
) -> ChairVerdict:
    return ChairVerdict(
        verdict=verdict,
        confidence=0.91,
        summary="secret summary text must not be stored",
        rationale="secret rationale text must not be stored",
        accepted_blockers=[
            ChairFinding(
                severity="HIGH",
                category="security",
                file=file_path,
                line_start=7,
                symbol_name="login",
                description=description,
                suggestion="secret suggestion text must not be stored",
                evidence_ref="secret evidence text must not be stored",
                policy_id="security.auth",
                source_reviewers=["secops"],
                chair_action="accepted",
                chair_reasoning="secret chair reasoning must not be stored",
            )
        ],
    )


def _record(repo_root, db_path, verdict: ChairVerdict | None = None, pack: ReviewPack | None = None):
    config = _config(db_path)
    return record_review_history(
        repo_root=repo_root,
        config=config,
        verdict=verdict or _verdict(),
        review_pack=pack if pack is not None else _review_pack(),
        reviewer_outputs=[
            ReviewerOutput(
                reviewer_id="secops",
                model="gemini/gemini-3-pro-preview",
                verdict="FAIL",
                findings=[],
                confidence=0.8,
                output_mode="prompt_json_fallback",
            )
        ],
        gate_result=None,
        ci_mode=False,
        staged=False,
        branch="main",
        audience="developer",
        output_modes=["terminal"],
        duration_ms=42,
    )


def test_resolve_history_path_defaults_to_os_cache_not_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-cache"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))

    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    resolved = resolve_history_path("", repo_root)

    expected_root = tmp_path / ("local-cache" if os.name == "nt" else "xdg-cache")
    assert resolved == (expected_root / "code-review-council" / "history.sqlite").resolve()
    assert repo_root not in resolved.parents


def test_resolve_history_path_accepts_repo_relative_override(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    assert resolve_history_path(".council-history.sqlite", repo_root) == (
        repo_root / ".council-history.sqlite"
    ).resolve()


def test_schema_creation_is_idempotent_and_versioned(tmp_path):
    db_path = tmp_path / "history.sqlite"
    conn = connect_history_db(db_path)
    try:
        ensure_schema(conn)
        ensure_schema(conn)
        assert current_schema_version(conn) == SCHEMA_VERSION
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {"_schema_migrations", "runs", "findings"}.issubset(tables)
    finally:
        conn.close()


def test_schema_rejects_future_version(tmp_path):
    db_path = tmp_path / "history.sqlite"
    conn = connect_history_db(db_path)
    try:
        conn.execute(
            "CREATE TABLE _schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_migrations(version, applied_at) VALUES (999, '2026-01-01T00:00:00Z')"
        )
        conn.commit()
        with pytest.raises(HistorySchemaError):
            ensure_schema(conn)
    finally:
        conn.close()


def test_safe_finding_storage_omits_forbidden_text_fields(tmp_path):
    db_path = tmp_path / "history.sqlite"

    _record(tmp_path, db_path)

    conn = connect_history_db(db_path)
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(findings)")}
        assert columns == {
            "run_id",
            "fingerprint",
            "severity",
            "category",
            "file_path",
            "reviewer_id",
            "policy_id",
            "verdict",
            "is_repeated",
            "debt_run_count",
        }
        row = conn.execute("SELECT * FROM findings").fetchone()
        assert row["severity"] == "HIGH"
        assert row["category"] == "security"
        assert row["file_path"] == "src/app.py"
        assert row["reviewer_id"] == "secops"
        assert row["policy_id"] == "security.auth"
        assert row["verdict"] == "accepted_blocker"
        assert row["is_repeated"] == 0
        assert row["debt_run_count"] == 1
    finally:
        conn.close()

    db_bytes = db_path.read_bytes()
    forbidden = [
        b"raw diff must not be stored",
        b"secret summary text",
        b"secret rationale text",
        b"repeatable unsafe auth check",
        b"secret suggestion text",
        b"secret evidence text",
        b"secret chair reasoning",
    ]
    assert all(value not in db_bytes for value in forbidden)


def test_retention_pruning_removes_expired_runs_and_cascades_findings(tmp_path):
    db_path = tmp_path / "history.sqlite"
    conn = connect_history_db(db_path)
    try:
        ensure_schema(conn)
        old = datetime.now(UTC) - timedelta(days=10)
        fresh = datetime.now(UTC)
        conn.execute(
            """
            INSERT INTO runs (
                id, repo_id, repo_display, created_at, ci_mode, audience, verdict,
                confidence, degraded, degraded_reasons_json, files_changed, lines_changed,
                token_estimate, languages_json, reviewer_models_json, output_modes_json,
                accepted_blockers_count, warnings_count, dismissed_count, total_findings_count,
                severity_counts_json, category_counts_json, duration_ms
            ) VALUES (?, ?, ?, ?, 0, 'developer', 'PASS', 1.0, 0, '[]', 0, 0, 0,
                '[]', '{}', '[]', 0, 0, 0, 0, '{}', '{}', 0)
            """,
            ("old-run", "repo", "repo", old.isoformat().replace("+00:00", "Z")),
        )
        conn.execute(
            """
            INSERT INTO runs (
                id, repo_id, repo_display, created_at, ci_mode, audience, verdict,
                confidence, degraded, degraded_reasons_json, files_changed, lines_changed,
                token_estimate, languages_json, reviewer_models_json, output_modes_json,
                accepted_blockers_count, warnings_count, dismissed_count, total_findings_count,
                severity_counts_json, category_counts_json, duration_ms
            ) VALUES (?, ?, ?, ?, 0, 'developer', 'PASS', 1.0, 0, '[]', 0, 0, 0,
                '[]', '{}', '[]', 0, 0, 0, 0, '{}', '{}', 0)
            """,
            ("fresh-run", "repo", "repo", fresh.isoformat().replace("+00:00", "Z")),
        )
        conn.execute(
            """
            INSERT INTO findings (
                run_id, fingerprint, severity, category, file_path, reviewer_id,
                policy_id, verdict, is_repeated, debt_run_count
            ) VALUES ('old-run', 'fp', 'HIGH', 'security', 'src/app.py',
                'secops', 'security.auth', 'accepted_blocker', 0, 1)
            """
        )
        conn.commit()

        pruned = prune_history(conn, "repo", retention_days=2)

        assert pruned == 1
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
        # The implementation deletes expired run rows only; SQLite FK cascade
        # owns dependent finding cleanup.
        assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 0
    finally:
        conn.close()


def test_summary_marks_repeat_candidates_and_debt_at_three_consecutive_runs(tmp_path):
    db_path = tmp_path / "history.sqlite"

    _record(tmp_path, db_path)
    _record(tmp_path, db_path)
    _record(tmp_path, db_path)

    summary = summarize_history(
        repo_root=tmp_path,
        history_config=_config(db_path).history,
        days=30,
        limit=10,
    )

    assert summary.total_runs == 3
    assert len(summary.repeats) == 1
    repeat = summary.repeats[0]
    assert repeat.run_count == 3
    assert repeat.consecutive_count == 3
    assert repeat.is_debt is True
    assert "[DEBT]" in "\n".join(format_history_summary(summary))


def test_summary_resets_debt_when_latest_run_lacks_fingerprint(tmp_path):
    db_path = tmp_path / "history.sqlite"

    _record(tmp_path, db_path)
    _record(tmp_path, db_path)
    empty_verdict = ChairVerdict(
        verdict="PASS",
        confidence=1.0,
        summary="clean",
        rationale="clean",
    )
    _record(tmp_path, db_path, verdict=empty_verdict, pack=_review_pack("clean diff"))

    summary = summarize_history(
        repo_root=tmp_path,
        history_config=_config(db_path).history,
        days=30,
        limit=10,
    )

    assert len(summary.repeats) == 1
    assert summary.repeats[0].run_count == 2
    assert summary.repeats[0].consecutive_count == 0
    assert summary.repeats[0].is_debt is False
    assert "[REPEAT]" in "\n".join(format_history_summary(summary))


def test_doctor_history_health_reports_info_for_healthy_store(tmp_path):
    health = check_history_health(tmp_path, _config(tmp_path / "history.sqlite").history)

    assert health.status == "INFO"
    assert "schema v" in health.detail
    assert health.remediation is None


def test_doctor_history_health_warns_for_write_failure(tmp_path):
    health = check_history_health(tmp_path, _config(tmp_path).history)

    assert health.status == "WARN"
    assert "failed" in health.detail.lower()


def test_doctor_history_health_warns_for_schema_mismatch(tmp_path):
    db_path = tmp_path / "history.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE _schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_migrations(version, applied_at) VALUES (999, '2026-01-01T00:00:00Z')"
        )
        conn.commit()
    finally:
        conn.close()

    health = check_history_health(tmp_path, _config(db_path).history)

    assert health.status == "WARN"
    assert "schema" in health.detail.lower()

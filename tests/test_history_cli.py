from __future__ import annotations

from typer.testing import CliRunner

from council.cli import app
from council.config import CouncilConfig, HistoryConfig
from council.history import record_review_history
from council.schemas import ChairFinding, ChairVerdict, ReviewPack


def _write_config(repo_root, db_name: str = "history.sqlite") -> None:
    (repo_root / ".council.toml").write_text(
        f"""
[history]
enabled = true
path = "{db_name}"
retention_days = 180
store_finding_text = false
""",
        encoding="utf-8",
    )


def _seed(repo_root, repeat_count: int) -> None:
    config = CouncilConfig(history=HistoryConfig(path="history.sqlite"))
    for _ in range(repeat_count):
        record_review_history(
            repo_root=repo_root,
            config=config,
            verdict=ChairVerdict(
                verdict="FAIL",
                confidence=0.9,
                summary="summary not stored",
                rationale="rationale not stored",
                accepted_blockers=[
                    ChairFinding(
                        severity="HIGH",
                        category="security",
                        file="src/app.py",
                        description="repeatable issue",
                        policy_id="security.auth",
                        source_reviewers=["secops"],
                        chair_action="accepted",
                    )
                ],
            ),
            review_pack=ReviewPack(
                diff_text="+secret diff not stored",
                changed_files=["src/app.py"],
                languages_detected=["python"],
                total_lines_changed=2,
                token_estimate=12,
            ),
            reviewer_outputs=[],
            gate_result=None,
            ci_mode=False,
            staged=False,
            branch="main",
            audience="developer",
            output_modes=["terminal"],
            duration_ms=10,
        )


def test_history_summary_command_handles_empty_history(tmp_path):
    _write_config(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["history", "summary", "--repo", str(tmp_path)])

    assert result.exit_code == 0
    assert "No history recorded" in result.output
    assert "history.sqlite" in result.output


def test_history_summary_command_shows_repeat_candidate(tmp_path):
    _write_config(tmp_path)
    _seed(tmp_path, repeat_count=2)
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["history", "summary", "--days", "30", "--limit", "10", "--repo", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert "[REPEAT]" in result.output
    assert "[DEBT]" not in result.output
    assert "fingerprint=" in result.output
    assert "secret diff not stored" not in result.output


def test_history_summary_command_marks_debt_at_three_consecutive_runs(tmp_path):
    _write_config(tmp_path)
    _seed(tmp_path, repeat_count=3)
    runner = CliRunner()

    result = runner.invoke(app, ["history", "summary", "--repo", str(tmp_path)])

    assert result.exit_code == 0
    assert "[DEBT]" in result.output
    assert "consecutive=3" in result.output

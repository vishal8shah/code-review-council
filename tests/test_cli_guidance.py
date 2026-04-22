from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from council.cli import app
from council.config import CouncilConfig, ReviewerConfig
from council.doctor import (
    DoctorCheck,
    DoctorReport,
    build_doctor_next_steps,
    build_review_profile,
)


def test_build_review_profile_summarizes_models_timeouts_and_policy():
    config = CouncilConfig(
        chair_model="gemini/gemini-3-pro-preview",
        timeout_seconds=360,
        reviewer_timeout_seconds=360,
        reviewer_concurrency=1,
        reviewers=[
            ReviewerConfig(
                id="qa",
                name="QA",
                model="gemini/gemini-3-pro-preview",
                enabled=True,
            )
        ],
    )

    profile = build_review_profile(config)

    assert "Chair model: gemini/gemini-3-pro-preview" in profile
    assert "Reviewers: qa:gemini/gemini-3-pro-preview" in profile
    assert "reviewer 360s" in profile[2]
    assert "concurrency 1" in profile[2]
    assert "Integrity policy: fail" in profile


def test_build_doctor_next_steps_distinguishes_pass_and_fail():
    passing = DoctorReport([DoctorCheck("api_keys", "PASS", "Keys found.")])
    failing = DoctorReport([DoctorCheck("api_keys", "FAIL", "Missing keys.")])

    assert build_doctor_next_steps(passing, branch="develop")[0] == (
        "Run `council review --branch develop` for a local advisory review."
    )
    assert build_doctor_next_steps(failing, branch="develop")[0] == (
        "Fix the FAIL checks above before running a review."
    )


def test_doctor_command_prints_profile_and_next_steps(tmp_path):
    runner = CliRunner()
    report = DoctorReport([DoctorCheck("api_keys", "PASS", "Keys found.")])

    with patch("council.doctor.run_doctor", return_value=report):
        result = runner.invoke(app, ["doctor", "--branch", "main", "--repo", str(tmp_path)])

    assert result.exit_code == 0
    assert "Review profile" in result.output
    assert "Recommended next steps" in result.output
    assert "council review --branch main" in result.output


def test_init_command_prints_onboarding_next_steps(tmp_path):
    runner = CliRunner()

    result = runner.invoke(app, ["init", "--repo", str(tmp_path)])

    assert result.exit_code == 0
    assert "Recommended next steps" in result.output
    assert "GOOGLE_API_KEY" in result.output
    assert "council doctor --branch main" in result.output
    assert "council review --branch main" in result.output

from __future__ import annotations

from pathlib import Path
import inspect
import tomllib

from typer.testing import CliRunner

from council import __version__
from council.cli import _app_callback, app


def test_version_option_reports_installed_version():
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"Code Review Council {__version__}"


def test_root_help_lists_version_option():
    version_option = inspect.signature(_app_callback).parameters["version"].default

    assert "--version" in version_option.param_decls


def test_package_version_matches_project_metadata():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert __version__ == pyproject["project"]["version"]


def test_package_metadata_positions_council_for_agentic_review():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]

    assert project["description"] == (
        "Evidence-based multi-agent AI code review gate for AI-generated pull requests"
    )
    assert {
        "ai-agents",
        "ai-generated-code",
        "ai-code-review",
        "claude-code",
        "codex",
        "github-actions",
        "pull-request",
    }.issubset(project["keywords"])
    assert project["urls"]["Security"].endswith("/security/advisories/new")
    assert project["urls"]["Roadmap"].endswith("/COMMERCIAL_READINESS.md")

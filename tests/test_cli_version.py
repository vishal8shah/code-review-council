from __future__ import annotations

from pathlib import Path
import tomllib

from typer.testing import CliRunner

from council import __version__
from council.cli import app


def test_version_option_reports_installed_version():
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"Code Review Council {__version__}"


def test_root_help_lists_version_option():
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "--version" in result.output


def test_package_version_matches_project_metadata():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert __version__ == pyproject["project"]["version"]

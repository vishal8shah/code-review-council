from __future__ import annotations

import pytest
from typer.testing import CliRunner

from council.cli import _DEFAULT_WORKFLOW_OPENAI_GATE, app


def _workflow_dir(root):
    return root / ".github" / "workflows"


@pytest.mark.parametrize("args", [[], ["--workflow-profile", "default"], ["--workflow-profile", "all"]])
def test_init_default_profiles_write_all_workflows(tmp_path, args):
    runner = CliRunner()

    result = runner.invoke(app, ["init", "--repo", str(tmp_path), *args])

    assert result.exit_code == 0
    workflow_dir = _workflow_dir(tmp_path)
    assert (workflow_dir / "council-review.yml").exists()
    assert (workflow_dir / "council-byok.yml").exists()
    assert (workflow_dir / "council-openai-gate.yml").exists()


def test_init_openai_gate_profile_writes_only_openai_gate_workflow(tmp_path):
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["init", "--repo", str(tmp_path), "--workflow-profile", "openai-gate"],
    )

    assert result.exit_code == 0
    workflow_dir = _workflow_dir(tmp_path)
    assert not (workflow_dir / "council-review.yml").exists()
    assert not (workflow_dir / "council-byok.yml").exists()
    assert (workflow_dir / "council-openai-gate.yml").exists()
    assert not (tmp_path / ".council.toml").exists()
    assert not (tmp_path / ".councilignore").exists()
    assert not (tmp_path / "prompts").exists()
    assert "OPENAI_API_KEY" in result.output
    assert "GOOGLE_API_KEY" not in result.output


def test_init_invalid_workflow_profile_fails_before_writing_files(tmp_path):
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["init", "--repo", str(tmp_path), "--workflow-profile", "gemini"],
    )

    assert result.exit_code == 1
    assert "Invalid --workflow-profile" in result.output
    assert not (tmp_path / ".council.toml").exists()
    assert not _workflow_dir(tmp_path).exists()


def test_openai_gate_workflow_scaffold_is_pinned_and_safe():
    assert "git+https://github.com/vishal8shah/code-review-council.git@v0.2.0" in (
        _DEFAULT_WORKFLOW_OPENAI_GATE
    )
    assert "git+https://github.com/vishal8shah/code-review-council.git@main" not in (
        _DEFAULT_WORKFLOW_OPENAI_GATE
    )
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in _DEFAULT_WORKFLOW_OPENAI_GATE
    assert 'chair_model = "openai/gpt-5.5"' in _DEFAULT_WORKFLOW_OPENAI_GATE
    assert 'chair_reasoning_effort = "medium"' in _DEFAULT_WORKFLOW_OPENAI_GATE
    assert 'model = "openai/gpt-5.2"' in _DEFAULT_WORKFLOW_OPENAI_GATE
    assert '--branch "$BASE_REF"' in _DEFAULT_WORKFLOW_OPENAI_GATE
    assert "BASE_REF: ${{ github.base_ref }}" in _DEFAULT_WORKFLOW_OPENAI_GATE

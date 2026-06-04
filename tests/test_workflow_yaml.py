from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from council import __version__
from council.cli import (
    _DEFAULT_WORKFLOW,
    _DEFAULT_WORKFLOW_BYOK,
    _DEFAULT_WORKFLOW_OPENAI_GATE,
)


GENERATED_WORKFLOWS = {
    "generated/council-review.yml": _DEFAULT_WORKFLOW,
    "generated/council-byok.yml": _DEFAULT_WORKFLOW_BYOK,
    "generated/council-openai-gate.yml": _DEFAULT_WORKFLOW_OPENAI_GATE,
}
CHECKED_IN_WORKFLOWS = {
    str(path): path.read_text(encoding="utf-8")
    for path in sorted(Path(".github/workflows").glob("*.yml"))
}


@pytest.mark.parametrize(
    ("workflow_name", "workflow"),
    [
        pytest.param(workflow_name, workflow, id=workflow_name)
        for workflow_name, workflow in {
            **GENERATED_WORKFLOWS,
            **CHECKED_IN_WORKFLOWS,
        }.items()
    ],
)
def test_workflow_yaml_is_parseable(workflow_name, workflow):
    parsed = yaml.safe_load(workflow)

    assert isinstance(parsed, dict), workflow_name
    assert isinstance(parsed.get("jobs"), dict), workflow_name


def test_release_smoke_default_matches_package_and_generated_gate():
    """Keep the package version, release smoke, and generated gate pin aligned."""
    release_smoke = yaml.load(
        Path(".github/workflows/release-smoke.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    release_tag = f"v{__version__}"

    assert release_smoke["on"]["workflow_dispatch"]["inputs"]["release_ref"]["default"] == release_tag
    assert (
        f"git+https://github.com/vishal8shah/code-review-council.git@{release_tag}"
        in _DEFAULT_WORKFLOW_OPENAI_GATE
    )

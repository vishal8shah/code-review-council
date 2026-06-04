from __future__ import annotations

from pathlib import Path

import pytest
import yaml

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

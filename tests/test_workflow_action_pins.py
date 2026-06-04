from __future__ import annotations

from pathlib import Path
import re

import pytest

from council.cli import (
    _DEFAULT_WORKFLOW,
    _DEFAULT_WORKFLOW_BYOK,
    _DEFAULT_WORKFLOW_OPENAI_GATE,
)


APPROVED_NODE24_ACTIONS = {
    "actions/checkout": ("df4cb1c069e1874edd31b4311f1884172cec0e10", "v6.0.3"),
    "actions/setup-python": ("a309ff8b426b58ec0e2a45f0f869d46889d02405", "v6.2.0"),
    "actions/upload-artifact": ("043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", "v7.0.1"),
    "actions/configure-pages": ("45bfe0192ca1faeb007ade9deae92b16b8254a0d", "v6.0.0"),
    "actions/upload-pages-artifact": ("fc324d3547104276b827a68afc52ff2a11cc49c9", "v5.0.0"),
    "actions/deploy-pages": ("cd2ce8fcbc39b97be8ca5fce6e763baed58fa128", "v5.0.0"),
}
ACTION_USE = re.compile(r"uses:\s+(actions/[\w-]+)@([0-9a-f]{40})\s+#\s+(\S+)")


def _assert_approved_action_pins(workflow: str) -> None:
    action_lines = [line for line in workflow.splitlines() if "uses: actions/" in line]
    matches = ACTION_USE.findall(workflow)

    assert len(matches) == len(action_lines)
    for action, sha, version in matches:
        assert action in APPROVED_NODE24_ACTIONS
        assert (sha, version) == APPROVED_NODE24_ACTIONS[action]


@pytest.mark.parametrize(
    "workflow",
    [_DEFAULT_WORKFLOW, _DEFAULT_WORKFLOW_BYOK, _DEFAULT_WORKFLOW_OPENAI_GATE],
)
def test_generated_workflows_use_approved_node24_action_pins(workflow):
    _assert_approved_action_pins(workflow)


@pytest.mark.parametrize("workflow_path", sorted(Path(".github/workflows").glob("*.yml")))
def test_checked_in_workflows_use_approved_node24_action_pins(workflow_path):
    _assert_approved_action_pins(workflow_path.read_text(encoding="utf-8"))

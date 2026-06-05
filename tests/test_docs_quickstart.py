from __future__ import annotations

from pathlib import Path

import yaml


def test_quickstart_page_is_in_docs_nav():
    mkdocs = yaml.load(
        Path("site/mkdocs.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )

    assert {"10 Minute Quickstart": "quickstart-10-min.md"} in mkdocs["nav"]


def test_quickstart_covers_first_value_path():
    page = Path("site/docs/quickstart-10-min.md").read_text(encoding="utf-8")

    required_snippets = [
        "council --version",
        "council init",
        "council doctor --branch main",
        "--output-json council-report.json",
        "--output-md council-review.md",
        "--audience owner",
        "--output-html owner-report.html",
        "council init --workflow-profile openai-gate",
        "degraded_reasons",
        "Owner mode is a presentation layer",
    ]
    for snippet in required_snippets:
        assert snippet in page

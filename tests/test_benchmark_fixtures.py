from __future__ import annotations

import json
from pathlib import Path

import yaml

from council.config import PreprocessorConfig
from council.diff_preprocessor import filter_context
from council.schemas import DiffContext, DiffFile


FIXTURE_ROOT = Path("benchmarks/seeded-prs/agentic-login-bypass")


def test_agentic_login_bypass_fixture_is_complete():
    expected_paths = [
        FIXTURE_ROOT / "README.md",
        FIXTURE_ROOT / "expected-findings.json",
        FIXTURE_ROOT / "base" / "src" / "billing" / "access.py.txt",
        FIXTURE_ROOT / "base" / "tests" / "access_test_sample.py.txt",
        FIXTURE_ROOT / "head" / "src" / "billing" / "access.py.txt",
        FIXTURE_ROOT / "head" / "tests" / "access_test_sample.py.txt",
    ]

    for path in expected_paths:
        assert path.exists(), path


def test_agentic_login_bypass_expected_findings_match_head_evidence():
    expected = json.loads((FIXTURE_ROOT / "expected-findings.json").read_text(encoding="utf-8"))
    finding = expected["expected_findings"][0]
    head_lines = (FIXTURE_ROOT / "head" / f"{finding['file']}.txt").read_text(
        encoding="utf-8"
    ).splitlines()
    evidence_window = "\n".join(head_lines[finding["line_start"] - 1 : finding["line_end"]])

    assert expected["expected_verdict"] == "FAIL"
    assert finding["severity"] == "HIGH"
    assert finding["category"] == "security"
    assert 'request_params.get("user_id")' in evidence_window
    assert "return requested_user == invoice.owner_id" in evidence_window
    assert expected["expected_warnings"][0]["file"] == "tests/access_test_sample.py"
    assert any("clean PASS" in item for item in expected["not_expected"])


def test_benchmark_docs_are_linked_from_nav_and_quickstart():
    mkdocs = yaml.load(
        Path("site/mkdocs.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("COMMERCIAL_READINESS.md").read_text(encoding="utf-8")
    benchmark_page = Path("site/docs/benchmarks.md").read_text(encoding="utf-8")
    quickstart = Path("site/docs/quickstart-10-min.md").read_text(encoding="utf-8")

    assert {"Benchmarks": "benchmarks.md"} in mkdocs["nav"]
    assert "site/docs/benchmarks.md" in readme
    assert "one seeded-risk fixture exists" in roadmap
    assert "agentic-login-bypass" in benchmark_page
    assert "council benchmarks validate" in benchmark_page
    assert "council benchmarks prepare-run" in benchmark_page
    assert "council benchmarks score" in benchmark_page
    assert "council init" in benchmark_page
    assert ".py.txt" in benchmark_page
    assert "expected-findings.json" in benchmark_page
    assert "Benchmarks" in quickstart


def test_seeded_risk_fixture_is_excluded_from_repo_self_review():
    councilignore = Path(".councilignore").read_text(encoding="utf-8")
    diff_context = DiffContext(
        files=[
            DiffFile(
                path="benchmarks/seeded-prs/agentic-login-bypass/head/src/billing/access.py.txt",
                change_type="added",
                additions=30,
            ),
            DiffFile(path="site/docs/benchmarks.md", change_type="added", additions=80),
        ],
        changed_files=[
            "benchmarks/seeded-prs/agentic-login-bypass/head/src/billing/access.py.txt",
            "site/docs/benchmarks.md",
        ],
    )

    filtered, skipped = filter_context(diff_context, PreprocessorConfig(), repo_root=Path("."))

    assert "package-lock.json" in councilignore
    assert "node_modules/" in councilignore
    assert "seeded-prs/" in councilignore
    assert skipped == ["benchmarks/seeded-prs/agentic-login-bypass/head/src/billing/access.py.txt"]
    assert [diff_file.path for diff_file in filtered.files] == ["site/docs/benchmarks.md"]

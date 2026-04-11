from __future__ import annotations

from council.config import CouncilConfig
from council.diff_preprocessor import filter_context, process
from council.review_pack import assemble
from council.schemas import DiffContext, DiffFile, DiffHunk


def test_review_pack_support_summaries_preserve_skipped_test_context(tmp_path):
    source_content = (
        "def parse_payload(raw: str) -> dict[str, str]:\n"
        "    return {\"raw\": raw}\n"
    )
    test_content = (
        "from council.llm_transport import extract_json_object\n\n"
        "def test_extract_json_object_handles_real_triple_backtick_fences():\n"
        "    assert extract_json_object('```json\\n{}\\n```') == '{}'\n\n"
        "def test_extract_json_object_handles_sentinel_fences():\n"
        "    assert extract_json_object('[TRIPLE_BACKTICK]json\\n{}\\n[TRIPLE_BACKTICK]') == '{}'\n"
    )

    diff_context = DiffContext(
        files=[
            DiffFile(
                path="council/llm_transport.py",
                language="python",
                change_type="modified",
                additions=2,
                hunks=[
                    DiffHunk(
                        source_start=1,
                        source_length=0,
                        target_start=1,
                        target_length=2,
                        content="+def parse_payload(raw: str) -> dict[str, str]:\n+    return {\"raw\": raw}\n",
                    )
                ],
                source_content=source_content,
            ),
            DiffFile(
                path="tests/test_llm_transport.py",
                language="python",
                change_type="modified",
                additions=42,
                hunks=[
                    DiffHunk(
                        source_start=1,
                        source_length=0,
                        target_start=1,
                        target_length=40,
                        content=(
                            "+def test_extract_json_object_handles_real_triple_backtick_fences():\n"
                            + "".join(f"+    assert True  # {i}\n" for i in range(20))
                            + "+def test_extract_json_object_handles_sentinel_fences():\n"
                            + "".join(f"+    assert True  # {i}\n" for i in range(20, 40))
                        ),
                    )
                ],
                source_content=test_content,
            ),
        ],
        changed_files=["council/llm_transport.py", "tests/test_llm_transport.py"],
        total_additions=44,
    )

    preprocessor_config = CouncilConfig().preprocessor.model_copy(
        update={"max_review_tokens": 40, "max_file_tokens": 1_000}
    )
    filtered_full_diff, filtered_skipped = filter_context(diff_context, preprocessor_config, repo_root=tmp_path)
    processed_diff, budget_skipped, truncated_files = process(
        filtered_full_diff,
        preprocessor_config,
        repo_root=tmp_path,
        reviewer_models=["openai/gpt-4o"],
    )
    review_pack = assemble(
        diff_context=processed_diff,
        metadata_context=filtered_full_diff,
        gate_zero_findings=[],
        config=CouncilConfig(),
        skipped_files=filtered_skipped + budget_skipped,
        truncated_files=truncated_files,
    )

    assert [diff_file.path for diff_file in processed_diff.files] == ["council/llm_transport.py"]
    assert any(
        symbol.name == "parse_payload" and symbol.has_tests and symbol.test_file == "tests/test_llm_transport.py"
        for symbol in review_pack.changed_symbols
    )

    summaries = {summary.path: summary for summary in review_pack.support_files_outside_budget}
    assert "tests/test_llm_transport.py" in summaries
    test_summary = summaries["tests/test_llm_transport.py"]
    assert test_summary.kind == "test"
    assert test_summary.status == "skipped"
    assert test_summary.related_files == ["council/llm_transport.py"]
    assert "test_extract_json_object_handles_real_triple_backtick_fences" in test_summary.summary
    assert len(test_summary.summary) <= 240


def test_review_pack_support_summaries_bound_docs_and_config_lines(tmp_path):
    diff_context = DiffContext(
        files=[
            DiffFile(
                path="README.md",
                language="markdown",
                change_type="modified",
                additions=6,
                hunks=[
                    DiffHunk(
                        source_start=1,
                        source_length=0,
                        target_start=1,
                        target_length=6,
                        content=(
                            "+## Phase 3\n"
                            "+### Transport\n"
                            "+### Fallbacks\n"
                            "+### Doctor\n"
                            "+Paragraph text\n"
                            "+Another paragraph\n"
                        ),
                    )
                ],
                source_content="## Phase 3\n### Transport\n### Fallbacks\n### Doctor\n",
            ),
            DiffFile(
                path=".github/workflows/council-review.yml",
                language="yaml",
                change_type="modified",
                additions=6,
                hunks=[
                    DiffHunk(
                        source_start=1,
                        source_length=0,
                        target_start=1,
                        target_length=6,
                        content=(
                            "+timeout-minutes: 30\n"
                            "+max-parallel: 1\n"
                            "+fail-fast: false\n"
                            "+permissions: read-all\n"
                        ),
                    )
                ],
                source_content="timeout-minutes: 30\nmax-parallel: 1\nfail-fast: false\npermissions: read-all\n",
            ),
        ],
        changed_files=["README.md", ".github/workflows/council-review.yml"],
        total_additions=12,
    )

    review_pack = assemble(
        diff_context=DiffContext(files=[], changed_files=[]),
        metadata_context=diff_context,
        gate_zero_findings=[],
        config=CouncilConfig(),
        skipped_files=["README.md", ".github/workflows/council-review.yml"],
        truncated_files=[],
    )

    summaries = {summary.path: summary for summary in review_pack.support_files_outside_budget}
    assert summaries["README.md"].kind == "docs"
    assert summaries["README.md"].summary.count("|") <= 2
    assert len(summaries["README.md"].summary) <= 240
    assert summaries[".github/workflows/council-review.yml"].kind == "config"
    assert "timeout-minutes" in summaries[".github/workflows/council-review.yml"].summary
    assert len(summaries[".github/workflows/council-review.yml"].summary) <= 240

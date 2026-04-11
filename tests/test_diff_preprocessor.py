from __future__ import annotations

from pathlib import Path

from council.config import PreprocessorConfig
from council.diff_preprocessor import effective_review_token_budget, filter_context, process
from council.schemas import DiffContext, DiffFile, DiffHunk


def test_effective_review_token_budget_caps_gpt4o_models():
    config = PreprocessorConfig(max_review_tokens=30_000)

    assert effective_review_token_budget(config, ["openai/gpt-5.2"]) == 30_000
    assert effective_review_token_budget(config, ["openai/gpt-4o"]) == 20_000
    assert effective_review_token_budget(config, ["openai/gpt-5.2", "openai/gpt-4o-mini"]) == 20_000


def test_filter_context_removes_ignored_and_generated_files(tmp_path: Path):
    (tmp_path / ".councilignore").write_text("package-lock.json\n", encoding="utf-8")

    diff_context = DiffContext(
        files=[
            DiffFile(path="package-lock.json", change_type="modified", additions=10),
            DiffFile(
                path="src/generated.py",
                change_type="modified",
                additions=2,
                source_content="# @generated\nvalue = 1\n",
            ),
            DiffFile(path="src/app.py", language="python", change_type="modified", additions=5),
        ],
        changed_files=["package-lock.json", "src/generated.py", "src/app.py"],
    )

    filtered, skipped = filter_context(diff_context, PreprocessorConfig(), repo_root=tmp_path)

    assert [diff_file.path for diff_file in filtered.files] == ["src/app.py"]
    assert skipped == ["package-lock.json", "src/generated.py"]


def test_process_respects_budget_after_filtering(tmp_path: Path):
    source_hunk = "def important() -> bool:\n    return True\n"
    test_hunk = "\n".join(f"assert important() is True  # {i}" for i in range(200))

    diff_context = DiffContext(
        files=[
            DiffFile(
                path="src/app.py",
                language="python",
                change_type="modified",
                additions=2,
                hunks=[DiffHunk(source_start=1, source_length=0, target_start=1, target_length=2, content=source_hunk)],
                source_content=source_hunk,
            ),
            DiffFile(
                path="tests/test_app.py",
                language="python",
                change_type="modified",
                additions=200,
                hunks=[DiffHunk(source_start=1, source_length=0, target_start=1, target_length=200, content=test_hunk)],
                source_content=test_hunk,
            ),
        ],
        changed_files=["src/app.py", "tests/test_app.py"],
        total_additions=202,
    )

    config = PreprocessorConfig(max_review_tokens=40, max_file_tokens=1_000)
    processed, skipped, truncated = process(
        diff_context,
        config,
        repo_root=tmp_path,
        reviewer_models=["openai/gpt-4o"],
    )

    assert [diff_file.path for diff_file in processed.files] == ["src/app.py"]
    assert skipped == ["tests/test_app.py"]
    assert truncated == ["tests/test_app.py"]

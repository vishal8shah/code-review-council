from __future__ import annotations

import logging
from pathlib import Path

from council.config import ContextConfig, CouncilConfig, PreprocessorConfig
from council.repo_context import build_repo_test_context
from council.review_pack import (
    _build_source_lookup_maps,
    _match_by_stem,
    _match_ecmascript_imports,
    _match_python_imports,
    assemble,
)
from council.schemas import DiffContext, DiffFile, DiffHunk


def _source_entry(path: str = "src/app.py") -> DiffFile:
    return DiffFile(path=path, change_type="modified", language="python")


def _context_config(**overrides) -> ContextConfig:
    return ContextConfig(**overrides)


def test_repo_context_maps_python_imports_from_explicit_repo_root(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "from src.app import parse_payload\n",
        encoding="utf-8",
    )

    context = build_repo_test_context(
        repo_root=tmp_path,
        source_entries=[_source_entry()],
        context_config=_context_config(),
        preprocessor_config=PreprocessorConfig(),
    )

    assert context.enabled is True
    assert context.scanned_test_files == ["tests/test_app.py"]
    assert context.coverage_map == {"src/app.py": ["tests/test_app.py"]}


def test_repo_context_normalizes_paths_before_councilignore(tmp_path):
    (tmp_path / ".councilignore").write_text("ignored/\n", encoding="utf-8")
    (tmp_path / "ignored" / "tests").mkdir(parents=True)
    (tmp_path / "ignored" / "tests" / "test_app.py").write_text(
        "from src.app import parse_payload\n",
        encoding="utf-8",
    )

    context = build_repo_test_context(
        repo_root=tmp_path,
        source_entries=[_source_entry()],
        context_config=_context_config(),
        preprocessor_config=PreprocessorConfig(),
    )

    assert context.scanned_test_files == []
    assert context.coverage_map == {}


def test_repo_context_skips_heavy_directories(tmp_path):
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "test_app.py").write_text(
        "from src.app import parse_payload\n",
        encoding="utf-8",
    )

    context = build_repo_test_context(
        repo_root=tmp_path,
        source_entries=[_source_entry()],
        context_config=_context_config(),
        preprocessor_config=PreprocessorConfig(),
    )

    assert context.scanned_test_files == []
    assert context.coverage_map == {}


def test_repo_context_caps_test_file_count(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    for name in ("test_app.py", "test_other.py"):
        (tests_dir / name).write_text("from src.app import parse_payload\n", encoding="utf-8")

    context = build_repo_test_context(
        repo_root=tmp_path,
        source_entries=[_source_entry()],
        context_config=_context_config(max_test_files=1),
        preprocessor_config=PreprocessorConfig(),
    )

    assert context.limited is True
    assert context.scanned_test_files == ["tests/test_app.py"]
    assert context.skipped_test_files == ["tests/test_other.py"]


def test_repo_context_skips_oversized_files_without_reading(tmp_path, monkeypatch):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    oversized = tests_dir / "test_app.py"
    oversized.write_text("x" * 25, encoding="utf-8")

    def fail_read_text(self, *args, **kwargs):
        if self == oversized:
            raise AssertionError("oversized file should not be read")
        return original_read_text(self, *args, **kwargs)

    original_read_text = Path.read_text
    monkeypatch.setattr(Path, "read_text", fail_read_text)

    context = build_repo_test_context(
        repo_root=tmp_path,
        source_entries=[_source_entry()],
        context_config=_context_config(max_test_file_bytes=10),
        preprocessor_config=PreprocessorConfig(),
    )

    assert context.limited is True
    assert context.scanned_test_files == []
    assert context.skipped_test_files == ["tests/test_app.py"]


def test_repo_context_read_errors_are_logged_and_nonfatal(tmp_path, monkeypatch, caplog):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    broken = tests_dir / "test_app.py"
    broken.write_text("from src.app import parse_payload\n", encoding="utf-8")
    original_read_text = Path.read_text

    def fail_read_text(self, *args, **kwargs):
        if self == broken:
            raise OSError("nope")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    with caplog.at_level(logging.WARNING):
        context = build_repo_test_context(
            repo_root=tmp_path,
            source_entries=[_source_entry()],
            context_config=_context_config(),
            preprocessor_config=PreprocessorConfig(),
        )

    assert context.limited is True
    assert context.skipped_test_files == ["tests/test_app.py"]
    assert "Could not read repo test context file tests/test_app.py" in caplog.text


def test_matching_helpers_cover_python_ecmascript_and_stem_cases():
    source_modules, ecmascript_sources = _build_source_lookup_maps([
        "src/app.py",
        "src/components/button.tsx",
        "src/components/card/index.ts",
        "src/utils/format.ts",
    ])

    assert _match_python_imports("from src.app import parse_payload\n", source_modules) == [
        "src/app.py"
    ]
    assert _match_ecmascript_imports(
        "src/components/__tests__/button.spec.tsx",
        "import { Button } from '../button'\nimport { Card } from '../card'\n",
        ecmascript_sources,
    ) == ["src/components/button.tsx", "src/components/card/index.ts"]
    assert _match_by_stem("src/utils/__tests__/format.spec.ts", ["src/utils/format.ts"]) == [
        "src/utils/format.ts"
    ]


def test_review_pack_repo_context_does_not_pollute_diff_local_map(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "from src.app import parse_payload\n",
        encoding="utf-8",
    )
    source = "def parse_payload(raw: str) -> dict[str, str]:\n    return {'raw': raw}\n"
    diff_context = DiffContext(
        files=[
            DiffFile(
                path="src/app.py",
                language="python",
                change_type="modified",
                source_content=source,
                hunks=[
                    DiffHunk(
                        source_start=1,
                        source_length=2,
                        target_start=1,
                        target_length=2,
                        content="+def parse_payload(raw: str) -> dict[str, str]:\n+    return {'raw': raw}\n",
                    )
                ],
            )
        ],
        changed_files=["src/app.py"],
    )

    review_pack = assemble(
        diff_context=diff_context,
        gate_zero_findings=[],
        config=CouncilConfig(),
        repo_root=tmp_path,
    )

    assert review_pack.test_coverage_map == {"src/app.py": []}
    assert review_pack.repo_test_context.coverage_map == {
        "src/app.py": ["tests/test_app.py"]
    }
    assert review_pack.changed_symbols[0].has_tests is True
    assert review_pack.changed_symbols[0].test_file == "tests/test_app.py"


def test_review_pack_disabled_context_skips_repo_scan(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "from src.app import parse_payload\n",
        encoding="utf-8",
    )
    config = CouncilConfig()
    config.context.full_repo_tests = False

    review_pack = assemble(
        diff_context=DiffContext(
            files=[DiffFile(path="src/app.py", language="python", change_type="modified")],
            changed_files=["src/app.py"],
        ),
        gate_zero_findings=[],
        config=config,
        repo_root=tmp_path,
    )

    assert review_pack.repo_test_context.enabled is False
    assert review_pack.repo_test_context.coverage_map == {}

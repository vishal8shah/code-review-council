"""Bounded repository context discovery for ReviewPack assembly."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .analyzers.base import is_test_file
from .config import ContextConfig, PreprocessorConfig
from .diff_preprocessor import _load_ignore_patterns, _should_ignore
from .review_pack import (
    _ECMASCRIPT_EXTENSIONS,
    _build_source_lookup_maps,
    _match_by_stem,
    _match_ecmascript_imports,
    _match_python_imports,
    _normalize_repo_path,
)
from .schemas import DiffFile, RepoTestContext

_log = logging.getLogger(__name__)

_HEAVY_DIRS = {
    ".git",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "venv",
    ".venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
}


def build_repo_test_context(
    *,
    repo_root: Path,
    source_entries: list[DiffFile],
    context_config: ContextConfig,
    preprocessor_config: PreprocessorConfig,
) -> RepoTestContext:
    """Discover existing repo tests for changed source files within safe caps."""
    repo_root = repo_root.resolve()
    source_paths = [entry.path for entry in source_entries if not is_test_file(entry.path)]
    if not source_paths:
        return RepoTestContext(enabled=True)

    source_modules, ecmascript_sources = _build_source_lookup_maps(source_paths)
    coverage_map: dict[str, list[str]] = {}
    scanned_test_files: list[str] = []
    skipped_test_files: list[str] = []
    limited = False
    ignore_patterns = _load_ignore_patterns(repo_root, preprocessor_config.ignore_file)

    try:
        for dirpath, dirnames, filenames in os.walk(repo_root):
            dirnames.sort()
            filenames.sort()
            kept_dirs: list[str] = []
            for dirname in dirnames:
                dir_path = Path(dirpath) / dirname
                rel_dir = _repo_relative_path(repo_root, dir_path)
                if _is_ignored_dir(rel_dir, ignore_patterns):
                    continue
                kept_dirs.append(dirname)
            dirnames[:] = kept_dirs

            for filename in filenames:
                file_path = Path(dirpath) / filename
                rel_path = _repo_relative_path(repo_root, file_path)
                if _should_ignore(rel_path, ignore_patterns):
                    continue
                if not is_test_file(rel_path):
                    continue
                if len(scanned_test_files) >= context_config.max_test_files:
                    limited = True
                    skipped_test_files.append(rel_path)
                    return RepoTestContext(
                        enabled=True,
                        scanned_test_files=scanned_test_files,
                        skipped_test_files=skipped_test_files,
                        limited=limited,
                        coverage_map=coverage_map,
                    )

                try:
                    if file_path.stat().st_size > context_config.max_test_file_bytes:
                        limited = True
                        skipped_test_files.append(rel_path)
                        continue
                    content = file_path.read_text(encoding="utf-8", errors="surrogateescape")
                except Exception as exc:
                    limited = True
                    skipped_test_files.append(rel_path)
                    _log.warning("Could not read repo test context file %s: %s", rel_path, exc)
                    continue

                scanned_test_files.append(rel_path)
                for source_path in _matched_sources(
                    test_path=rel_path,
                    test_source=content,
                    source_modules=source_modules,
                    ecmascript_sources=ecmascript_sources,
                    source_paths=source_paths,
                ):
                    coverage_map.setdefault(source_path, [])
                    if rel_path not in coverage_map[source_path]:
                        coverage_map[source_path].append(rel_path)
    except Exception as exc:
        limited = True
        _log.warning("Could not scan repo test context under %s: %s", repo_root, exc)

    return RepoTestContext(
        enabled=True,
        scanned_test_files=scanned_test_files,
        skipped_test_files=skipped_test_files,
        limited=limited,
        coverage_map=coverage_map,
    )


def _repo_relative_path(repo_root: Path, path: Path) -> str:
    return _normalize_repo_path(path.relative_to(repo_root).as_posix())


def _is_ignored_dir(repo_relative_path: str, ignore_patterns: list[str]) -> bool:
    name = _path_name(repo_relative_path)
    return (
        name in _HEAVY_DIRS
        or name.endswith(".egg-info")
        or _should_ignore(repo_relative_path, ignore_patterns)
        or _should_ignore(f"{repo_relative_path}/", ignore_patterns)
    )


def _matched_sources(
    *,
    test_path: str,
    test_source: str,
    source_modules: dict[str, str],
    ecmascript_sources: dict[str, str],
    source_paths: list[str],
) -> list[str]:
    suffix = Path(test_path).suffix.lower()
    matched_paths: list[str] = []
    if suffix == ".py":
        matched_paths = _match_python_imports(test_source, source_modules)
    elif suffix in _ECMASCRIPT_EXTENSIONS:
        matched_paths = _match_ecmascript_imports(test_path, test_source, ecmascript_sources)
    if not matched_paths:
        matched_paths = _match_by_stem(test_path, source_paths)
    return matched_paths


def _path_name(repo_relative_path: str) -> str:
    """Return the final normalized path segment without importing pathlib internals."""
    return repo_relative_path.rstrip("/").split("/")[-1]

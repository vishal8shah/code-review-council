"""Language-specific analyzer base class.

Each language has an analyzer plugin: doc checks, type checks, etc.
Python uses ast.parse(); TypeScript/JavaScript use lightweight export heuristics.
Parser-backed analysis can be added later if needed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import GateZeroFinding

_TEST_FILE_SUFFIXES = (
    "_test.py",
    ".test.ts",
    ".test.tsx",
    ".spec.ts",
    ".spec.tsx",
    ".test.js",
    ".test.jsx",
    ".spec.js",
    ".spec.jsx",
)


def _normalized_path_parts(file_path: str) -> tuple[str, ...]:
    """Return lowercase path segments for repo-relative paths across slash styles."""
    normalized = file_path.replace("\\", "/").strip("/")
    return tuple(part.lower() for part in normalized.split("/") if part and part != ".")


def is_test_file(file_path: str) -> bool:
    """Return True for explicit test-file conventions, not arbitrary nested folders."""
    parts = _normalized_path_parts(file_path)
    if not parts:
        return False

    name = parts[-1]
    return (
        parts[0] == "tests"
        or "__tests__" in parts[:-1]
        or name == "conftest.py"
        or name.startswith("test_")
        or name.endswith(_TEST_FILE_SUFFIXES)
    )


class BaseAnalyzer(ABC):
    """Abstract base for language-specific static analyzers."""

    extensions: list[str] = []

    @abstractmethod
    def check_docs(self, source: str, file_path: str) -> list[GateZeroFinding]: ...

    @abstractmethod
    def check_types(self, source: str, file_path: str) -> list[GateZeroFinding]: ...

    def check_all(self, source: str, file_path: str) -> list[GateZeroFinding]:
        """Run all checks for this language."""
        findings: list[GateZeroFinding] = []
        findings.extend(self.check_docs(source, file_path))
        findings.extend(self.check_types(source, file_path))
        return findings

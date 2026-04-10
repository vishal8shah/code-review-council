"""Language-specific analyzer base class.

Each language has an analyzer plugin: doc checks, type checks, etc.
Python uses ast.parse(); TypeScript/JavaScript use lightweight export heuristics.
Parser-backed analysis can be added later if needed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

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


def is_test_file(file_path: str) -> bool:
    """Return True when file path represents test or support-test code."""
    path = Path(file_path)
    posix = path.as_posix()
    name = path.name.lower()
    return (
        posix.startswith("tests/")
        or "/tests/" in f"/{posix}"
        or posix.startswith("__tests__/")
        or "/__tests__/" in f"/{posix}"
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

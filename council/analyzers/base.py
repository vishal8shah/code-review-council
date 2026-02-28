"""Language-specific analyzer base class.

Each language has an analyzer plugin: doc checks, type checks, etc.
Python uses ast.parse(); other languages would use tree-sitter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import GateZeroFinding


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

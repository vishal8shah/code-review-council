"""JavaScript-specific Gate Zero analyzer using parser-free export heuristics."""

from __future__ import annotations

from ..schemas import GateZeroFinding
from .base import BaseAnalyzer, is_test_file
from .ecmascript import collect_javascript_exports, has_leading_jsdoc


def _function_label(name: str) -> str:
    """Format a function name for finding messages."""
    return f"`{name}()`"


class JavaScriptAnalyzer(BaseAnalyzer):
    """Static analysis for JavaScript files via line-based export detection."""

    extensions = [".js", ".jsx"]

    def check_docs(self, source: str, file_path: str) -> list[GateZeroFinding]:
        """Require JSDoc for exported functions and classes."""
        if is_test_file(file_path):
            return []

        findings: list[GateZeroFinding] = []
        for symbol in collect_javascript_exports(source):
            if not symbol.requires_docs or has_leading_jsdoc(source, symbol.line_no):
                continue

            if symbol.kind == "class":
                message = f"Class `{symbol.name}` is missing a leading JSDoc block"
            else:
                message = f"Function {_function_label(symbol.name)} is missing a leading JSDoc block"

            findings.append(
                GateZeroFinding(
                    check="docstring",
                    severity="CRITICAL",
                    category="documentation",
                    file=file_path,
                    line_start=symbol.line_no,
                    line_end=symbol.line_no,
                    message=message,
                    suggestion="Add a JSDoc block describing purpose, params, and return value",
                )
            )

        return findings

    def check_types(self, source: str, file_path: str) -> list[GateZeroFinding]:
        """JavaScript Phase 1 does not enforce type annotations."""
        if is_test_file(file_path):
            return []
        return []

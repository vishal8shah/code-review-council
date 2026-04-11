"""TypeScript-specific Gate Zero analyzer using parser-free export heuristics."""

from __future__ import annotations

from ..schemas import GateZeroFinding
from .base import BaseAnalyzer, is_test_file
from .ecmascript import (
    collect_typescript_exports,
    has_leading_jsdoc,
    parameter_has_annotation,
    split_parameters,
)


def _function_label(name: str) -> str:
    """Format a function name for finding messages."""
    return f"`{name}()`"


class TypeScriptAnalyzer(BaseAnalyzer):
    """Static analysis for TypeScript files via line-based export detection."""

    extensions = [".ts", ".tsx"]

    def check_docs(self, source: str, file_path: str) -> list[GateZeroFinding]:
        """Require JSDoc for exported functions and classes."""
        if is_test_file(file_path):
            return []

        findings: list[GateZeroFinding] = []
        for symbol in collect_typescript_exports(source):
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
        """Require explicit parameter and return types for exported functions."""
        if is_test_file(file_path):
            return []

        findings: list[GateZeroFinding] = []
        for symbol in collect_typescript_exports(source):
            if not symbol.requires_types:
                continue

            if not symbol.return_annotation:
                findings.append(
                    GateZeroFinding(
                        check="type_hint",
                        severity="HIGH",
                        category="documentation",
                        file=file_path,
                        line_start=symbol.line_no,
                        message=(
                            f"Function {_function_label(symbol.name)} is missing return type annotation"
                        ),
                        suggestion="Add an explicit return type annotation",
                    )
                )

            for param in split_parameters(symbol.params):
                param_name = param.strip()
                if not param_name or parameter_has_annotation(param_name):
                    continue

                findings.append(
                    GateZeroFinding(
                        check="type_hint",
                        severity="MEDIUM",
                        category="documentation",
                        file=file_path,
                        line_start=symbol.line_no,
                        message=(
                            f"Parameter `{param_name}` in {_function_label(symbol.name)} "
                            "is missing type annotation"
                        ),
                        suggestion=f"Add a type annotation for `{param_name}`",
                    )
                )

        return findings

"""Python-specific Gate Zero analyzer.

Uses ast.parse() for fast, reliable AST analysis of Python files.
Checks docstrings and type annotations on public functions/classes.
"""

from __future__ import annotations

import ast

from ..schemas import GateZeroFinding
from .base import BaseAnalyzer


class PythonAnalyzer(BaseAnalyzer):
    """Static analysis for Python files via ast module."""

    extensions = [".py", ".pyi"]

    def check_docs(self, source: str, file_path: str) -> list[GateZeroFinding]:
        """Check that all public functions and classes have docstrings."""
        findings: list[GateZeroFinding] = []

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return findings  # can't parse → skip (linter will catch syntax errors)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue

            # Skip private/dunder methods (except __init__)
            if node.name.startswith("_") and node.name != "__init__":
                continue

            has_docstring = (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(getattr(node.body[0], "value", None), ast.Constant)
                and isinstance(node.body[0].value.value, str)
            )

            if not has_docstring:
                kind = "Class" if isinstance(node, ast.ClassDef) else "Function"
                findings.append(
                    GateZeroFinding(
                        check="docstring",
                        severity="CRITICAL",
                        category="documentation",
                        file=file_path,
                        line_start=node.lineno,
                        line_end=node.end_lineno,
                        message=f"{kind} `{node.name}()` is missing a docstring",
                        suggestion="Add a docstring describing purpose, params, and return value",
                    )
                )

        return findings

    def check_types(self, source: str, file_path: str) -> list[GateZeroFinding]:
        """Check that public functions have type annotations."""
        findings: list[GateZeroFinding] = []

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            # Skip private/dunder methods
            if node.name.startswith("_") and node.name != "__init__":
                continue

            # Check return type annotation (skip __init__ — returns None implicitly)
            if node.returns is None and node.name != "__init__":
                findings.append(
                    GateZeroFinding(
                        check="type_hint",
                        severity="HIGH",
                        category="documentation",
                        file=file_path,
                        line_start=node.lineno,
                        message=f"Function `{node.name}()` is missing return type annotation",
                        suggestion="Add a return type annotation (e.g., -> str, -> None)",
                    )
                )

            # Check parameter annotations (skip 'self' and 'cls')
            for arg in node.args.args:
                if arg.arg in ("self", "cls"):
                    continue
                if arg.annotation is None:
                    findings.append(
                        GateZeroFinding(
                            check="type_hint",
                            severity="MEDIUM",
                            category="documentation",
                            file=file_path,
                            line_start=node.lineno,
                            message=(
                                f"Parameter `{arg.arg}` in `{node.name}()` "
                                f"is missing type annotation"
                            ),
                            suggestion=f"Add type annotation for `{arg.arg}`",
                        )
                    )

        return findings

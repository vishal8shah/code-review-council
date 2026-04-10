"""Shared parser-free helpers for TypeScript and JavaScript analyzers."""

from __future__ import annotations

import re
from dataclasses import dataclass

_IDENTIFIER = r"[A-Za-z_$][A-Za-z0-9_$]*"
_FUNCTION_RE = re.compile(
    rf"""
    ^\s*export\s+
    (?:default\s+)?
    (?:async\s+)?
    function
    (?:\s+(?P<name>{_IDENTIFIER}))?
    (?:\s*<[^>]+>)?
    \s*\((?P<params>[^)]*)\)
    \s*(?::\s*(?P<return>[^\{{]+))?
    """,
    re.VERBOSE,
)
_CLASS_RE = re.compile(
    rf"^\s*export\s+(?:default\s+)?class(?:\s+(?P<name>{_IDENTIFIER}))?\b"
)
_INTERFACE_RE = re.compile(rf"^\s*export\s+interface\s+(?P<name>{_IDENTIFIER})\b")
_TYPE_RE = re.compile(rf"^\s*export\s+type\s+(?P<name>{_IDENTIFIER})\b")
_FUNCTION_EXPR_RE = re.compile(
    rf"""
    ^\s*export\s+
    (?:const|let|var)\s+
    (?P<name>{_IDENTIFIER})
    \s*=\s*
    (?:async\s*)?
    function
    (?:\s+{_IDENTIFIER})?
    \s*\((?P<params>[^)]*)\)
    \s*(?::\s*(?P<return>[^\{{]+))?
    """,
    re.VERBOSE,
)
_ARROW_RE = re.compile(
    rf"""
    ^\s*export\s+
    (?:const|let|var)\s+
    (?P<name>{_IDENTIFIER})
    \s*=\s*
    (?:async\s*)?
    (?:
        \((?P<params>[^)]*)\)
        |
        (?P<single>{_IDENTIFIER}(?:\s*\??\s*:\s*[^=]+)?)
    )
    \s*(?::\s*(?P<return>[^=]+))?
    \s*=>
    """,
    re.VERBOSE,
)


@dataclass(slots=True)
class ExportedSymbol:
    """A parser-free exported symbol descriptor."""

    name: str
    kind: str
    line_no: int
    params: str | None = None
    return_annotation: str | None = None
    requires_docs: bool = False
    requires_types: bool = False


def _normalize_name(name: str | None) -> str:
    """Return a stable display name for named and anonymous default exports."""
    return name or "default export"


def _strip_outer_parens(params: str) -> str:
    """Remove a single outer pair of parentheses from an arrow parameter list."""
    stripped = params.strip()
    if stripped.startswith("(") and stripped.endswith(")"):
        return stripped[1:-1]
    return stripped


def _match_symbol(
    pattern: re.Pattern[str],
    line: str,
    *,
    kind: str,
    line_no: int,
    requires_docs: bool,
    requires_types: bool,
) -> ExportedSymbol | None:
    """Create a symbol descriptor when a pattern matches a line."""
    match = pattern.match(line)
    if not match:
        return None

    params = match.groupdict().get("params")
    single = match.groupdict().get("single")
    if params is None and single:
        params = single
    if params is not None:
        params = _strip_outer_parens(params)

    return_annotation = match.groupdict().get("return")
    if return_annotation is not None:
        return_annotation = return_annotation.strip()

    return ExportedSymbol(
        name=_normalize_name(match.groupdict().get("name")),
        kind=kind,
        line_no=line_no,
        params=params,
        return_annotation=return_annotation,
        requires_docs=requires_docs,
        requires_types=requires_types,
    )


def collect_typescript_exports(source: str) -> list[ExportedSymbol]:
    """Collect exported TypeScript symbols with lightweight line-based heuristics."""
    symbols: list[ExportedSymbol] = []
    for line_no, line in enumerate(source.splitlines(), start=1):
        symbol = (
            _match_symbol(
                _FUNCTION_RE,
                line,
                kind="function",
                line_no=line_no,
                requires_docs=True,
                requires_types=True,
            )
            or _match_symbol(
                _CLASS_RE,
                line,
                kind="class",
                line_no=line_no,
                requires_docs=True,
                requires_types=False,
            )
            or _match_symbol(
                _INTERFACE_RE,
                line,
                kind="interface",
                line_no=line_no,
                requires_docs=False,
                requires_types=False,
            )
            or _match_symbol(
                _TYPE_RE,
                line,
                kind="type",
                line_no=line_no,
                requires_docs=False,
                requires_types=False,
            )
            or _match_symbol(
                _FUNCTION_EXPR_RE,
                line,
                kind="function",
                line_no=line_no,
                requires_docs=True,
                requires_types=True,
            )
            or _match_symbol(
                _ARROW_RE,
                line,
                kind="function",
                line_no=line_no,
                requires_docs=True,
                requires_types=True,
            )
        )
        if symbol is not None:
            symbols.append(symbol)
    return symbols


def collect_javascript_exports(source: str) -> list[ExportedSymbol]:
    """Collect exported JavaScript functions and classes."""
    symbols: list[ExportedSymbol] = []
    for line_no, line in enumerate(source.splitlines(), start=1):
        symbol = (
            _match_symbol(
                _FUNCTION_RE,
                line,
                kind="function",
                line_no=line_no,
                requires_docs=True,
                requires_types=False,
            )
            or _match_symbol(
                _CLASS_RE,
                line,
                kind="class",
                line_no=line_no,
                requires_docs=True,
                requires_types=False,
            )
            or _match_symbol(
                _FUNCTION_EXPR_RE,
                line,
                kind="function",
                line_no=line_no,
                requires_docs=True,
                requires_types=False,
            )
            or _match_symbol(
                _ARROW_RE,
                line,
                kind="function",
                line_no=line_no,
                requires_docs=True,
                requires_types=False,
            )
        )
        if symbol is not None:
            symbols.append(symbol)
    return symbols


def has_leading_jsdoc(source: str, line_no: int) -> bool:
    """Return True when the previous non-blank block is a JSDoc comment."""
    lines = source.splitlines()
    index = line_no - 2
    if index < 0 or not lines:
        return False
    if not lines[index].strip():
        return False

    current = index
    while current >= 0:
        stripped = lines[current].strip()
        if stripped.startswith("/**"):
            return True
        if stripped.startswith("*") or stripped.endswith("*/"):
            current -= 1
            continue
        return False

    return False


def split_parameters(params: str | None) -> list[str]:
    """Split a parameter list while ignoring commas inside nested delimiters."""
    if not params or not params.strip():
        return []

    parts: list[str] = []
    current: list[str] = []
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    angle_depth = 0
    in_string: str | None = None

    for char in params:
        if in_string:
            current.append(char)
            if char == in_string:
                in_string = None
            continue

        if char in {"'", '"', "`"}:
            in_string = char
        elif char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth = max(paren_depth - 1, 0)
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth = max(bracket_depth - 1, 0)
        elif char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth = max(brace_depth - 1, 0)
        elif char == "<":
            angle_depth += 1
        elif char == ">":
            angle_depth = max(angle_depth - 1, 0)
        elif (
            char == ","
            and paren_depth == 0
            and bracket_depth == 0
            and brace_depth == 0
            and angle_depth == 0
        ):
            candidate = "".join(current).strip()
            if candidate:
                parts.append(candidate)
            current = []
            continue

        current.append(char)

    candidate = "".join(current).strip()
    if candidate:
        parts.append(candidate)
    return parts


def parameter_has_annotation(param: str) -> bool:
    """Return True when a parameter has an explicit TypeScript annotation."""
    text = param.strip()
    if not text:
        return True

    if text.startswith(("...",)):
        text = text[3:].lstrip()

    if text == "this":
        return True

    if text.startswith("{") or text.startswith("["):
        return True

    if "=" in text:
        text = text.split("=", 1)[0].rstrip()

    return ":" in text

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


@dataclass(slots=True)
class _SplitState:
    """Track parameter parsing state across nested delimiters and strings."""

    paren_depth: int = 0
    bracket_depth: int = 0
    brace_depth: int = 0
    angle_depth: int = 0
    in_string: str | None = None


_STRING_DELIMITERS = {"'", '"', "`"}
_OPEN_DELIMITERS = {
    "(": "paren_depth",
    "[": "bracket_depth",
    "{": "brace_depth",
    "<": "angle_depth",
}
_CLOSE_DELIMITERS = {
    ")": "paren_depth",
    "]": "bracket_depth",
    "}": "brace_depth",
    ">": "angle_depth",
}


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
    """Collect exported TypeScript symbols from raw source text.

    Args:
        source: Full TypeScript or TSX source text to scan line by line.

    Returns:
        A list of ``ExportedSymbol`` records describing exported functions,
        classes, interfaces, type aliases, and function-valued variables found
        by the lightweight regex-based heuristics in this module.
    """
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
    state = _SplitState()

    for char in params:
        if _consume_string_character(state, char, current):
            continue

        if _start_string(state, char):
            current.append(char)
            continue

        if char == "," and _at_top_level(state):
            _flush_parameter(parts, current)
            current = []
            continue

        _update_nesting_depth(state, char)
        current.append(char)

    _flush_parameter(parts, current)
    return parts


def _consume_string_character(state: _SplitState, char: str, current: list[str]) -> bool:
    """Append a character while inside a quoted string and close it when needed."""
    if state.in_string is None:
        return False

    current.append(char)
    if char == state.in_string:
        state.in_string = None
    return True


def _start_string(state: _SplitState, char: str) -> bool:
    """Mark the beginning of a quoted string literal."""
    if char not in _STRING_DELIMITERS:
        return False

    state.in_string = char
    return True


def _update_nesting_depth(state: _SplitState, char: str) -> None:
    """Update delimiter nesting depth for the current character."""
    attr = _OPEN_DELIMITERS.get(char)
    if attr is not None:
        setattr(state, attr, getattr(state, attr) + 1)
        return

    attr = _CLOSE_DELIMITERS.get(char)
    if attr is not None:
        setattr(state, attr, max(getattr(state, attr) - 1, 0))


def _at_top_level(state: _SplitState) -> bool:
    """Return True when parsing is not nested inside any delimiter or string."""
    return (
        state.in_string is None
        and state.paren_depth == 0
        and state.bracket_depth == 0
        and state.brace_depth == 0
        and state.angle_depth == 0
    )


def _flush_parameter(parts: list[str], current: list[str]) -> None:
    """Append the buffered parameter text when it is non-empty."""
    candidate = "".join(current).strip()
    if candidate:
        parts.append(candidate)


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

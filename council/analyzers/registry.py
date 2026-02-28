"""Analyzer registry — maps file extensions to language-specific analyzers."""

from __future__ import annotations

from pathlib import Path

from .base import BaseAnalyzer
from .python import PythonAnalyzer

# Register all available analyzers
_ANALYZERS: list[type[BaseAnalyzer]] = [
    PythonAnalyzer,
    # TypeScriptAnalyzer and JavaScriptAnalyzer will be added in future
]

# Build extension → analyzer mapping
_REGISTRY: dict[str, type[BaseAnalyzer]] = {}
for analyzer_cls in _ANALYZERS:
    for ext in analyzer_cls.extensions:
        _REGISTRY[ext] = analyzer_cls


def get_analyzer(file_path: str) -> BaseAnalyzer | None:
    """Get the appropriate analyzer for a file based on its extension.

    Returns None if no analyzer is registered for this file type.
    """
    ext = Path(file_path).suffix.lower()
    analyzer_cls = _REGISTRY.get(ext)
    return analyzer_cls() if analyzer_cls else None


def supported_extensions() -> list[str]:
    """Return all file extensions with registered analyzers."""
    return list(_REGISTRY.keys())

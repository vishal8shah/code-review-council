"""Configuration loader for the Code Review Council.

Reads .council.toml from the repo root and provides typed settings.
Falls back to sensible defaults for everything.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


# ---------------------------------------------------------------------------
# Settings models
# ---------------------------------------------------------------------------


class EnforcementConfig(BaseModel):
    """How the council enforces verdicts."""

    mode: Literal["ci", "local", "both"] = "ci"
    ci_block_on: Literal["FAIL", "PASS_WITH_WARNINGS"] = "FAIL"
    local_mode: Literal["advisory", "gate"] = "advisory"
    on_integrity_issue: Literal["fail", "warn", "ignore"] = "fail"


class PreprocessorPriorities(BaseModel):
    """File priority weights for token budget allocation."""

    security: int = 10
    business: int = 7
    tests: int = 4
    config: int = 2
    docs: int = 1


class PreprocessorConfig(BaseModel):
    """Diff preprocessor settings."""

    max_review_tokens: int = 30_000
    max_file_tokens: int = 8_000
    ignore_file: str = ".councilignore"
    detect_generated: bool = True
    priorities: PreprocessorPriorities = PreprocessorPriorities()


class GateZeroLintersConfig(BaseModel):
    """Per-language lint commands."""

    python: str = "ruff check --diff"
    typescript: str = ""
    javascript: str = ""


class GateZeroConfig(BaseModel):
    """Gate Zero static analysis settings."""

    require_docs: bool = True
    require_type_annotations: bool = True
    require_readme_on_new_module: bool = True
    check_secrets: bool = True
    max_file_lines: int = 1000
    linters: GateZeroLintersConfig = GateZeroLintersConfig()
    analyzers: dict[str, bool] = {"python": True, "typescript": False, "javascript": False}


class ReviewerConfig(BaseModel):
    """Configuration for a single reviewer persona."""

    id: str
    name: str
    model: str
    prompt: str = ""  # path to prompt file, relative to repo root
    class_path: str = ""  # optional dotted import path for custom reviewer class
    enabled: bool = True
    focus: list[str] = []


class ReportersConfig(BaseModel):
    """Output reporter settings."""

    terminal: bool = True
    markdown: bool = True
    json_report: str | bool = "ci"  # "ci" = auto-enabled with --ci; true = always; false = never
    github_pr: bool = False  # not yet implemented — enable when reporter is added


class CostConfig(BaseModel):
    """Cost tracking settings."""

    warn_threshold_usd: float = 1.00
    budget_daily_usd: float = 20.00


class PresentationConfig(BaseModel):
    """Output presentation settings.

    Controls which audience the generated reports target.
    Absence of a [presentation] section in .council.toml defaults to developer.
    """

    default_audience: Literal["developer", "owner"] = "developer"


class CouncilConfig(BaseModel):
    """Top-level council configuration — the full .council.toml schema."""

    chair_model: str = "openai/gpt-4o"
    fail_on: Literal["FAIL", "PASS_WITH_WARNINGS"] = "FAIL"
    timeout_seconds: int = 60
    reviewer_concurrency: int = 2

    enforcement: EnforcementConfig = EnforcementConfig()
    preprocessor: PreprocessorConfig = PreprocessorConfig()
    gate_zero: GateZeroConfig = GateZeroConfig()
    reviewers: list[ReviewerConfig] = []
    reporters: ReportersConfig = ReportersConfig()
    cost: CostConfig = CostConfig()
    presentation: PresentationConfig = PresentationConfig()

    @property
    def active_reviewers(self) -> list[ReviewerConfig]:
        """Return only enabled reviewers."""
        return [r for r in self.reviewers if r.enabled]


# ---------------------------------------------------------------------------
# Default reviewer configurations
# ---------------------------------------------------------------------------

DEFAULT_REVIEWERS: list[dict[str, Any]] = [
    {
        "id": "secops",
        "name": "Security Operations Reviewer",
        "model": "anthropic/claude-sonnet-4-20250514",
        "prompt": "prompts/secops.md",
        "enabled": True,
    },
    {
        "id": "qa",
        "name": "QA Engineer",
        "model": "anthropic/claude-sonnet-4-20250514",
        "prompt": "prompts/qa.md",
        "enabled": True,
    },
    {
        "id": "architect",
        "name": "Solutions Architect",
        "model": "anthropic/claude-sonnet-4-20250514",
        "prompt": "prompts/architecture.md",
        "enabled": True,
    },
    {
        "id": "docs",
        "name": "Documentation Reviewer",
        "model": "anthropic/claude-sonnet-4-20250514",
        "prompt": "prompts/docs.md",
        "enabled": True,
    },
]


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


def load_config(repo_root: Path | None = None) -> CouncilConfig:
    """Load council configuration from .council.toml.

    Falls back to defaults if no config file exists.
    """
    if repo_root is None:
        repo_root = Path.cwd()

    config_path = repo_root / ".council.toml"
    raw: dict[str, Any] = {}

    if config_path.exists():
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)

    # Extract council-level settings
    council_raw = raw.get("council", {})
    enforcement_raw = council_raw.pop("enforcement", {})
    preprocessor_raw = raw.get("preprocessor", {})
    gate_zero_raw = raw.get("gate_zero", {})
    reporters_raw = raw.get("reporters", {})
    cost_raw = raw.get("cost", {})
    presentation_raw = raw.get("presentation", {})

    # Parse reviewers — support both [[reviewers]] and [[reviewers.custom]]
    reviewer_list = raw.get("reviewers", DEFAULT_REVIEWERS)
    if isinstance(reviewer_list, dict):
        # TOML [[reviewers.custom]] creates a dict with "custom" key
        reviewer_list = reviewer_list.get("custom", DEFAULT_REVIEWERS)
    if not reviewer_list:
        reviewer_list = DEFAULT_REVIEWERS

    return CouncilConfig(
        **council_raw,
        enforcement=EnforcementConfig(**enforcement_raw),
        preprocessor=PreprocessorConfig(**preprocessor_raw),
        gate_zero=GateZeroConfig(**gate_zero_raw),
        reviewers=[ReviewerConfig(**r) for r in reviewer_list],
        reporters=ReportersConfig(**reporters_raw),
        cost=CostConfig(**cost_raw),
        presentation=PresentationConfig(**presentation_raw),
    )

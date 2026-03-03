"""Pydantic schemas for the Code Review Council.

Every data boundary in the system is defined here. Reviewers consume ReviewPack,
produce ReviewerOutput. The Chair consumes ReviewerOutputs, produces ChairVerdict.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Gate Zero / Static Analysis
# ---------------------------------------------------------------------------


class GateZeroFinding(BaseModel):
    """A deterministic finding from Gate Zero static checks."""

    check: str  # e.g., "docstring", "type_hint", "secret", "lint", "readme"
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    category: Literal[
        "security", "testing", "architecture", "documentation", "performance", "style"
    ]
    file: str
    line_start: int | None = None
    line_end: int | None = None
    message: str
    suggestion: str | None = None
    auto_fixed: bool = False


class GateZeroResult(BaseModel):
    """Aggregate result of all Gate Zero checks."""

    passed: bool
    hard_fail: bool = False  # true if any check is configured as a hard blocker
    findings: list[GateZeroFinding] = []
    duration_ms: int = 0

    def as_early_exit(self) -> "ChairVerdict":
        """Convert Gate Zero hard-fail into a ChairVerdict for early exit."""
        return ChairVerdict(
            verdict="FAIL",
            confidence=1.0,
            degraded=False,
            summary=f"Gate Zero hard-fail: {len(self.findings)} issue(s) found before LLM review.",
            accepted_blockers=[
                ChairFinding(
                    severity=f.severity,
                    category=f.category,
                    file=f.file,
                    line_start=f.line_start,
                    line_end=f.line_end,
                    description=f.message,
                    suggestion=f.suggestion or "",
                    policy_id=f"gate_zero.{f.check}",
                    confidence=1.0,
                    source_reviewers=["gate_zero"],
                    consensus=True,
                    chair_action="accepted",
                    chair_reasoning="Deterministic Gate Zero check — not subject to Chair review.",
                )
                for f in self.findings
                if f.severity in ("CRITICAL", "HIGH")
            ],
            dismissed_findings=[],
            all_findings=[],
            reviewer_agreement_score=1.0,
            rationale="Gate Zero detected hard-fail issues. LLM review was skipped.",
        )


# ---------------------------------------------------------------------------
# Diff Context
# ---------------------------------------------------------------------------


class DiffFile(BaseModel):
    """A single file in the diff."""

    path: str
    language: str | None = None
    change_type: Literal["added", "modified", "deleted", "renamed"]
    additions: int = 0
    deletions: int = 0
    hunks: list[DiffHunk] = []
    source_content: str | None = None  # full file content (for AST analysis)


class DiffHunk(BaseModel):
    """A contiguous block of changes within a file."""

    source_start: int
    source_length: int
    target_start: int
    target_length: int
    content: str  # the raw hunk text


class DiffContext(BaseModel):
    """Parsed git diff with structured per-file, per-hunk data."""

    files: list[DiffFile] = []
    changed_files: list[str] = []
    added_files: list[str] = []
    deleted_files: list[str] = []
    branch: str = ""
    commit_range: str = ""
    total_additions: int = 0
    total_deletions: int = 0


# ---------------------------------------------------------------------------
# ReviewPack — The canonical input to all LLM reviewers
# ---------------------------------------------------------------------------


class ChangedSymbol(BaseModel):
    """A function, class, or export that was modified in the diff."""

    name: str
    kind: Literal["function", "class", "method", "export", "route", "schema", "other"]
    file: str
    line_start: int
    line_end: int
    change_type: Literal["added", "modified", "deleted"]
    signature: str | None = None  # e.g., "def parse_node(xml: str) -> Node"
    has_tests: bool = False
    test_file: str | None = None


class ReviewPack(BaseModel):
    """Structured context assembled once, consumed by all reviewers.

    This is the key architectural decision: reviewers get enriched context,
    not raw diff text. This produces evidence-backed, not opinion-based, reviews.
    """

    # Diff content (filtered and preprocessed)
    diff_text: str
    changed_files: list[str] = []
    added_files: list[str] = []
    deleted_files: list[str] = []

    # Enriched context
    changed_symbols: list[ChangedSymbol] = []
    test_coverage_map: dict[str, list[str]] = {}  # {source_file: [test_files]}
    languages_detected: list[str] = []

    # Policy context
    gate_zero_results: list[GateZeroFinding] = []
    repo_policies: dict[str, Any] = {}

    # Metadata
    branch: str = ""
    commit_range: str = ""
    total_lines_changed: int = 0
    token_estimate: int = 0
    files_truncated: list[str] = []
    files_skipped: list[str] = []


# ---------------------------------------------------------------------------
# Reviewer Output
# ---------------------------------------------------------------------------


class Finding(BaseModel):
    """A single finding from an LLM reviewer — enriched with evidence fields."""

    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    category: Literal[
        "security", "testing", "architecture", "documentation", "performance", "style"
    ]
    file: str
    line_start: int | None = None
    line_end: int | None = None
    symbol_name: str | None = None
    symbol_kind: str | None = None
    description: str
    suggestion: str = ""
    evidence_ref: str | None = None  # specific code snippet or diff hunk cited
    policy_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)


class ReviewerOutput(BaseModel):
    """Structured output from a single LLM reviewer."""

    reviewer_id: str
    model: str
    verdict: Literal["PASS", "FAIL"]
    findings: list[Finding] = []
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    tokens_used: int = 0
    error: str | None = None  # set if reviewer timed out or failed


# ---------------------------------------------------------------------------
# Chair Verdict
# ---------------------------------------------------------------------------


class ChairFinding(BaseModel):
    """Finding enriched by Chair with adjudication metadata."""

    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    category: Literal[
        "security", "testing", "architecture", "documentation", "performance", "style"
    ]
    file: str
    line_start: int | None = None
    line_end: int | None = None
    symbol_name: str | None = None
    description: str
    suggestion: str = ""
    evidence_ref: str | None = None
    policy_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    source_reviewers: list[str] = []
    consensus: bool = False
    chair_action: Literal["accepted", "dismissed", "downgraded", "upgraded"]
    chair_reasoning: str = ""


class ChairVerdict(BaseModel):
    """The final council verdict — produced by the Chair or Gate Zero early exit."""

    verdict: Literal["PASS", "PASS_WITH_WARNINGS", "FAIL"]
    confidence: float = Field(ge=0.0, le=1.0)
    degraded: bool = False  # true if any reviewer failed/timed out/had parse errors
    degraded_reasons: list[str] = []  # specific integrity issues that caused degraded state
    summary: str
    accepted_blockers: list[ChairFinding] = []
    warnings: list[ChairFinding] = []          # non-blocking accepted findings
    dismissed_findings: list[ChairFinding] = []
    all_findings: list[ChairFinding] = []
    reviewer_agreement_score: float = Field(ge=0.0, le=1.0, default=1.0)
    rationale: str = ""
    # Owner presentation — populated only when --audience owner is requested
    owner_presentation: "OwnerPresentation | None" = None


# ---------------------------------------------------------------------------
# Owner Presentation Layer
# ---------------------------------------------------------------------------


class OwnerFindingView(BaseModel):
    """Owner-audience view of a single accepted finding.

    This is a translation of a technical ChairFinding into plain English
    for product owners and semi-technical stakeholders.
    """

    title: str  # Short, plain-English title
    severity_label: str  # e.g. "Critical Security Issue", "Warning"
    urgency: Literal["fix_before_merge", "fix_soon", "nice_to_have"]
    plain_explanation: str  # What is wrong, in plain English
    why_it_matters: str  # Business / product impact
    fix_prompt: str  # Copy/paste prompt for an AI coding assistant
    test_after_fix: str  # What to verify after the fix is applied
    involve_engineer: str | None = None  # When to loop in a real developer


class OwnerPresentation(BaseModel):
    """Owner-audience presentation layer generated from a ChairVerdict.

    This is NOT a second set of findings. It is a translation of the same
    accepted findings into language suitable for product owners.
    """

    headline: str  # One-line summary of the overall situation
    merge_recommendation: Literal["SAFE_TO_MERGE", "MERGE_WITH_CAUTION", "FIX_BEFORE_MERGE"]
    risk_level: Literal["low", "medium", "high", "critical"]
    confidence_label: str  # e.g. "High confidence", "Moderate confidence"
    short_summary: str  # 2-3 sentence plain-English executive summary
    findings: list[OwnerFindingView] = []
    degraded_warning: str | None = None  # Set if the review run was degraded

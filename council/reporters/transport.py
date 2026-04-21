"""Shared report helpers for transport-mode visibility."""

from __future__ import annotations

from ..llm_transport import collect_transport_notes, output_mode_label
from ..schemas import ChairVerdict, ReviewerOutput


def transport_notes(
    verdict: ChairVerdict,
    reviewer_outputs: list[ReviewerOutput] | None = None,
) -> list[str]:
    """Return user-facing transport notes for reports."""
    return collect_transport_notes(verdict, reviewer_outputs)


def reviewer_output_mode(reviewer: ReviewerOutput) -> str:
    """Return a compact reviewer transport label for tables."""
    return output_mode_label(reviewer.output_mode)

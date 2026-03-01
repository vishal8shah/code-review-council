"""Orchestrator — runs the full Code Review Council pipeline.

Stage 0:    Gate Zero (deterministic static checks)
Stage 0.5:  Diff Preprocessing (filter, chunk, budget)
Stage 0.75: ReviewPack Assembly (structured context)
Stage 1:    Reviewer Panel (parallel LLM calls)
Stage 2:    Chair Synthesis (evidence-based adjudication)
Stage 3:    Report Generation
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from pathlib import Path

from . import chair as chair_module
from . import diff_preprocessor, gate_zero, review_pack as rp_module
from .config import CouncilConfig, ReviewerConfig
from .diff_parser import get_git_diff, parse_diff
from .reviewers.architecture import ArchitectReviewer
from .reviewers.base import BaseReviewer, _integrity_verdict
from .reviewers.docs import DocsReviewer
from .reviewers.qa import QAReviewer
from .reviewers.secops import SecOpsReviewer
from .schemas import (
    ChairVerdict,
    DiffContext,
    GateZeroResult,
    ReviewerOutput,
    ReviewPack,
)

logger = logging.getLogger(__name__)


class CouncilResult:
    """Full result of a council run, including auxiliary data for reporters."""

    def __init__(
        self,
        verdict: ChairVerdict,
        review_pack: ReviewPack | None = None,
        reviewer_outputs: list[ReviewerOutput] | None = None,
        gate_result: GateZeroResult | None = None,
    ):
        self.verdict = verdict
        self.review_pack = review_pack
        self.reviewer_outputs = reviewer_outputs or []
        self.gate_result = gate_result

# Map reviewer IDs to their classes
REVIEWER_CLASSES: dict[str, type[BaseReviewer]] = {
    "secops": SecOpsReviewer,
    "qa": QAReviewer,
    "architect": ArchitectReviewer,
    "docs": DocsReviewer,
}


def _load_class_path(class_path: str) -> type[BaseReviewer] | None:
    """Load a reviewer class from a 'module.path:ClassName' string."""
    try:
        module_path, class_name = class_path.rsplit(":", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        if not (isinstance(cls, type) and issubclass(cls, BaseReviewer)):
            logger.warning(
                "class_path %s resolved to %s which is not a BaseReviewer subclass — using BaseReviewer",
                class_path, cls,
            )
            return None
        return cls
    except Exception as e:
        logger.warning("Failed to load class_path %s: %s — using BaseReviewer", class_path, e)
        return None


def _instantiate_reviewers(
    configs: list[ReviewerConfig],
    on_integrity_issue: str = "fail",
    repo_root: Path | None = None,
) -> list[BaseReviewer]:
    """Create reviewer instances from config."""
    reviewers: list[BaseReviewer] = []
    for rc in configs:
        # Resolve class: class_path > builtin > BaseReviewer
        cls: type[BaseReviewer] | None = None
        if rc.class_path:
            cls = _load_class_path(rc.class_path)
        if cls is None:
            cls = REVIEWER_CLASSES.get(rc.id, BaseReviewer)

        # Resolve prompt path relative to repo_root
        prompt_path: str | None = None
        if rc.prompt and repo_root:
            resolved = (repo_root / rc.prompt).resolve()
            if resolved.is_relative_to(repo_root.resolve()):
                prompt_path = str(resolved)
            else:
                logger.warning(
                    "Prompt path %s escapes repo root — ignoring", rc.prompt
                )
        elif rc.prompt:
            prompt_path = rc.prompt

        reviewers.append(cls(
            reviewer_id=rc.id,
            model=rc.model,
            prompt_path=prompt_path,
            on_integrity_issue=on_integrity_issue,
        ))
    return reviewers


async def run_council(
    repo_root: Path | None = None,
    config: CouncilConfig | None = None,
    staged: bool = False,
    branch: str | None = None,
    diff_text: str | None = None,
) -> CouncilResult:
    """Run the full Code Review Council pipeline.

    Args:
        repo_root: Path to the git repo root.
        config: Council configuration. Loaded from .council.toml if None.
        staged: If True, review staged changes.
        branch: Branch to diff against (e.g., "main").
        diff_text: Pre-supplied diff text (for testing). Skips git call.

    Returns:
        CouncilResult with verdict and all auxiliary data.
    """
    if config is None:
        from .config import load_config
        config = load_config(repo_root)

    integrity_policy = config.enforcement.on_integrity_issue

    # Get diff
    if diff_text is None:
        diff_text = get_git_diff(repo_root=repo_root, staged=staged, branch=branch)

    if not diff_text.strip():
        return CouncilResult(
            verdict=ChairVerdict(
                verdict="PASS",
                confidence=1.0,
                summary="No changes detected.",
                rationale="Empty diff — nothing to review.",
            )
        )

    # Parse diff into structured context
    diff_context: DiffContext = parse_diff(diff_text, repo_root=repo_root)

    # Stage 0: Gate Zero (deterministic static checks)
    gate_result = gate_zero.check(diff_context, config, repo_root=repo_root)
    if gate_result.hard_fail:
        return CouncilResult(
            verdict=gate_result.as_early_exit(),
            gate_result=gate_result,
        )

    # Stage 0.5: Diff Preprocessing (filter, chunk, budget)
    processed_diff, skipped_files, truncated_files = diff_preprocessor.process(
        diff_context,
        config=config.preprocessor,
        repo_root=repo_root,
    )

    # Stage 0.75: Assemble ReviewPack
    review_pack = rp_module.assemble(
        diff_context=processed_diff,
        gate_zero_findings=gate_result.findings,
        config=config,
        skipped_files=skipped_files,
        truncated_files=truncated_files,
    )

    # Stage 1: Fan-out to all reviewers in parallel
    active_reviewers = config.active_reviewers
    reviewer_instances = _instantiate_reviewers(
        active_reviewers,
        on_integrity_issue=integrity_policy,
        repo_root=repo_root,
    )

    if not reviewer_instances:
        return CouncilResult(
            verdict=ChairVerdict(
                verdict="PASS",
                confidence=0.5,
                degraded=True,
                summary="No reviewers configured or all disabled.",
                rationale="Cannot produce a verdict without active reviewers.",
            ),
            review_pack=review_pack,
            gate_result=gate_result,
        )

    # Run all reviewers in parallel with exception handling
    tasks = [reviewer.review(review_pack) for reviewer in reviewer_instances]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Separate successes from failures
    reviewer_outputs: list[ReviewerOutput] = []
    failed_reviewers: list[str] = []
    integrity_issues: list[str] = []

    for reviewer, result in zip(reviewer_instances, results):
        if isinstance(result, Exception):
            # asyncio.gather exception — error above BaseReviewer.review()
            failed_reviewers.append(reviewer.reviewer_id)
            integrity_issues.append(
                f"{reviewer.reviewer_id}: reviewer_task_exception — {type(result).__name__}: {result}"
            )
            reviewer_outputs.append(
                ReviewerOutput(
                    reviewer_id=reviewer.reviewer_id,
                    model=reviewer.model,
                    verdict=_integrity_verdict(integrity_policy),
                    findings=[],
                    confidence=0.0,
                    reasoning="",
                    tokens_used=0,
                    error=f"Reviewer failed: {type(result).__name__}: {result}",
                )
            )
        else:
            reviewer_outputs.append(result)
            # Check for reviewer-level integrity issues (parse errors, dropped findings)
            if result.error:
                integrity_issues.append(f"{result.reviewer_id}: {result.error}")
            # Path E: FAIL with no findings and no error — internally inconsistent
            if (
                result.verdict == "FAIL"
                and len(result.findings) == 0
                and result.error is None
            ):
                integrity_issues.append(
                    f"{result.reviewer_id}: FAIL with no findings (schema/integrity)"
                )

    degraded = len(integrity_issues) > 0

    # Stage 2: Chair synthesis
    verdict = await chair_module.synthesize(
        review_pack=review_pack,
        reviews=reviewer_outputs,
        chair_model=config.chair_model,
        degraded=degraded,
        degraded_reasons=integrity_issues if integrity_issues else None,
        timeout=float(config.timeout_seconds),
    )

    return CouncilResult(
        verdict=verdict,
        review_pack=review_pack,
        reviewer_outputs=reviewer_outputs,
        gate_result=gate_result,
    )

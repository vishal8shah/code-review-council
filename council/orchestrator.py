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
from importlib import import_module
from pathlib import Path

from . import chair as chair_module
from . import diff_preprocessor, gate_zero, review_pack as rp_module
from .config import CouncilConfig, ReviewerConfig
from .diff_parser import get_git_diff, parse_diff
from .reviewers.architecture import ArchitectReviewer
from .reviewers.base import BaseReviewer
from .reviewers.docs import DocsReviewer
from .reviewers.qa import QAReviewer
from .reviewers.secops import SecOpsReviewer
from .schemas import ChairVerdict, DiffContext, GateZeroResult, ReviewerOutput, ReviewPack


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




def _is_integrity_error(error: str | None) -> bool:
    """Return True only for integrity-classified reviewer errors."""
    if not error:
        return False
    normalized = error.strip().lower()
    return (
        normalized.startswith("integrity issue:")
        or "reviewer_task_exception" in normalized
        or "invalid json" in normalized
    )

REVIEWER_CLASSES: dict[str, type[BaseReviewer]] = {
    "secops": SecOpsReviewer,
    "qa": QAReviewer,
    "architect": ArchitectReviewer,
    "docs": DocsReviewer,
}


def _load_class_path(class_path: str) -> type[BaseReviewer] | None:
    """Load class from dotted path. Returns None on invalid path/import."""
    if not class_path or "." not in class_path:
        return None
    try:
        module_name, class_name = class_path.rsplit(".", 1)
        module = import_module(module_name)
        cls = getattr(module, class_name)
        if isinstance(cls, type) and issubclass(cls, BaseReviewer):
            return cls
    except Exception:
        return None
    return None


def _instantiate_reviewers(
    configs: list[ReviewerConfig],
    on_integrity_issue: str,
    repo_root: Path | None = None,
) -> list[BaseReviewer]:
    """Create reviewer instances from config."""
    reviewers: list[BaseReviewer] = []
    base_root = repo_root or Path.cwd()

    for rc in configs:
        cls = _load_class_path(rc.class_path) if rc.class_path else None
        if cls is None:
            cls = REVIEWER_CLASSES.get(rc.id, BaseReviewer)

        prompt_path: str | None = None
        if rc.prompt:
            p = Path(rc.prompt)
            if not p.is_absolute():
                p = base_root / p
            prompt_path = str(p)

        try:
            reviewers.append(cls(
                reviewer_id=rc.id,
                model=rc.model,
                prompt_path=prompt_path,
                on_integrity_issue=on_integrity_issue,
            ))
        except TypeError as exc:
            msg = str(exc)
            if "on_integrity_issue" in msg and "unexpected keyword" in msg:
                # Backward compatibility for custom reviewers not yet accepting integrity policy kwarg
                reviewers.append(cls(
                    reviewer_id=rc.id,
                    model=rc.model,
                    prompt_path=prompt_path,
                ))
            else:
                raise
    return reviewers


async def run_council(
    repo_root: Path | None = None,
    config: CouncilConfig | None = None,
    staged: bool = False,
    branch: str | None = None,
    diff_text: str | None = None,
) -> CouncilResult:
    """Run the full Code Review Council pipeline."""
    if config is None:
        from .config import load_config
        config = load_config(repo_root)

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

    diff_context: DiffContext = parse_diff(diff_text, repo_root=repo_root)

    gate_result = gate_zero.check(diff_context, config, repo_root=repo_root)
    if gate_result.hard_fail:
        return CouncilResult(verdict=gate_result.as_early_exit(), gate_result=gate_result)

    processed_diff, skipped_files, truncated_files = diff_preprocessor.process(
        diff_context,
        config=config.preprocessor,
        repo_root=repo_root,
    )

    review_pack = rp_module.assemble(
        diff_context=processed_diff,
        gate_zero_findings=gate_result.findings,
        config=config,
        skipped_files=skipped_files,
        truncated_files=truncated_files,
    )

    reviewer_instances = _instantiate_reviewers(
        config.active_reviewers,
        config.enforcement.on_integrity_issue,
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

    tasks = [reviewer.review(review_pack) for reviewer in reviewer_instances]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    reviewer_outputs: list[ReviewerOutput] = []
    integrity_issues: list[str] = []

    for reviewer, result in zip(reviewer_instances, results):
        if isinstance(result, Exception):
            integrity_issues.append(f"{reviewer.reviewer_id}: reviewer_task_exception: {type(result).__name__}")
            reviewer_outputs.append(
                ReviewerOutput(
                    reviewer_id=reviewer.reviewer_id,
                    model=reviewer.model,
                    verdict="FAIL" if config.enforcement.on_integrity_issue == "fail" else "PASS",
                    findings=[],
                    confidence=0.0,
                    reasoning="",
                    tokens_used=0,
                    error=f"reviewer_task_exception: {type(result).__name__}: {result}",
                    integrity_error=True,
                )
            )
            continue

        reviewer_outputs.append(result)
        if result.integrity_error or _is_integrity_error(result.error):
            integrity_issues.append(f"{result.reviewer_id}: {result.error}")

        if result.verdict == "FAIL" and not result.findings and result.error is None:
            integrity_issues.append(
                f"{result.reviewer_id}: integrity issue: FAIL verdict with no findings/evidence"
            )

    degraded = len(integrity_issues) > 0

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

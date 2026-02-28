"""Base reviewer — handles LLM calls, ReviewPack serialization, response parsing."""

from __future__ import annotations

import json
from pathlib import Path

import litellm

from ..schemas import Finding, ReviewPack, ReviewerOutput


class BaseReviewer:
    """Base class for all LLM reviewer personas."""

    reviewer_id: str = "base"

    def __init__(self, reviewer_id: str, model: str, prompt_path: str | None = None, timeout: float = 60.0):
        """Initialize a reviewer."""
        self.reviewer_id = reviewer_id
        self.model = model
        self._prompt_path = prompt_path
        self.timeout = timeout

    def get_system_prompt(self) -> str:
        """Get the system prompt. Loads from file if available, else uses built-in."""
        if self._prompt_path:
            p = Path(self._prompt_path)
            if p.exists():
                return p.read_text(encoding="utf-8")
        return self._default_prompt()

    def _default_prompt(self) -> str:
        """Override in subclasses to provide a built-in prompt."""
        return (
            "You are a code reviewer. Analyze the provided ReviewPack and produce "
            "structured findings in JSON format."
        )

    def _build_user_message(self, review_pack: ReviewPack) -> str:
        """Serialize the ReviewPack for the LLM.

        Includes all enriched context: symbols, test map, Gate Zero results,
        skipped/truncated file lists, and the diff itself.
        """
        symbols_summary = ""
        if review_pack.changed_symbols:
            symbols_summary = "\n## Changed Symbols\n"
            for s in review_pack.changed_symbols:
                test_status = "has tests" if s.has_tests else "NO tests"
                symbols_summary += (
                    f"- `{s.signature or s.name}` ({s.kind}, {s.change_type}) "
                    f"in {s.file}:{s.line_start}-{s.line_end} [{test_status}]\n"
                )

        test_map_summary = ""
        if review_pack.test_coverage_map:
            test_map_summary = "\n## Test Coverage Map (files in this diff only)\n"
            for src, tests in review_pack.test_coverage_map.items():
                if tests:
                    test_map_summary += f"- {src} -> {', '.join(tests)}\n"
                else:
                    test_map_summary += f"- {src} -> NO TEST FILES IN DIFF\n"

        gate_zero_summary = ""
        if review_pack.gate_zero_results:
            gate_zero_summary = "\n## Gate Zero Static Analysis Results\n"
            for g in review_pack.gate_zero_results:
                loc = f"{g.file}:{g.line_start}" if g.line_start else g.file
                gate_zero_summary += f"- [{g.severity}] {g.check}: {loc} — {g.message}\n"

        skipped_summary = ""
        if review_pack.files_skipped:
            skipped_summary = (
                f"\n## Files Skipped by Preprocessor\n"
                f"{', '.join(review_pack.files_skipped)}\n"
            )
        if review_pack.files_truncated:
            skipped_summary += (
                f"\n## Files Truncated (token budget)\n"
                f"{', '.join(review_pack.files_truncated)}\n"
            )

        policies_summary = ""
        if review_pack.repo_policies:
            policies_summary = "\n## Active Repo Policies\n"
            for key, val in review_pack.repo_policies.items():
                policies_summary += f"- {key}: {val}\n"

        return f"""# Code Review Pack

## Metadata
- Branch: {review_pack.branch}
- Files changed: {len(review_pack.changed_files)}
- Lines changed: {review_pack.total_lines_changed}
- Languages: {', '.join(review_pack.languages_detected) or 'unknown'}
{symbols_summary}{test_map_summary}{gate_zero_summary}{skipped_summary}{policies_summary}
## Diff
```diff
{review_pack.diff_text}
```

Respond with ONLY valid JSON:
{{
  "verdict": "PASS" or "FAIL",
  "confidence": 0.0-1.0,
  "findings": [
    {{
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "category": "security|testing|architecture|documentation|performance|style",
      "file": "path/to/file",
      "line_start": 42,
      "line_end": 55,
      "symbol_name": "function_name",
      "description": "What is wrong",
      "suggestion": "How to fix it",
      "evidence_ref": "The specific code that demonstrates the issue",
      "confidence": 0.9
    }}
  ],
  "reasoning": "Overall assessment"
}}"""

    async def review(self, review_pack: ReviewPack) -> ReviewerOutput:
        """Run the review via LiteLLM."""
        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": self._build_user_message(review_pack)},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                timeout=self.timeout,
                num_retries=2,
            )
            raw = response.choices[0].message.content or "{}"
            tokens_used = response.usage.total_tokens if response.usage else 0
            return self._parse_response(raw, tokens_used)
        except Exception as e:
            return ReviewerOutput(
                reviewer_id=self.reviewer_id,
                model=self.model,
                verdict="PASS",
                confidence=0.0,
                tokens_used=0,
                error=f"{type(e).__name__}: {e}",
            )

    def _parse_response(self, raw_json: str, tokens_used: int) -> ReviewerOutput:
        """Parse LLM JSON into ReviewerOutput."""
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            return ReviewerOutput(
                reviewer_id=self.reviewer_id, model=self.model,
                verdict="PASS", confidence=0.0, tokens_used=tokens_used,
                error=f"Invalid JSON: {raw_json[:200]}",
            )

        findings: list[Finding] = []
        malformed_count = 0
        for f in data.get("findings", []):
            try:
                findings.append(Finding(
                    severity=f.get("severity", "LOW"),
                    category=f.get("category", "style"),
                    file=f.get("file", "unknown"),
                    line_start=f.get("line_start"),
                    line_end=f.get("line_end"),
                    symbol_name=f.get("symbol_name"),
                    symbol_kind=f.get("symbol_kind"),
                    description=f.get("description", ""),
                    suggestion=f.get("suggestion", ""),
                    evidence_ref=f.get("evidence_ref"),
                    policy_id=f.get("policy_id"),
                    confidence=f.get("confidence", 0.8),
                ))
            except Exception:
                malformed_count += 1
                continue

        # If significant findings were dropped, flag as degraded
        error_msg = None
        if malformed_count > 0:
            total_raw = len(data.get("findings", []))
            error_msg = f"Parsed {len(findings)}/{total_raw} findings ({malformed_count} malformed/dropped)"

        return ReviewerOutput(
            reviewer_id=self.reviewer_id,
            model=self.model,
            verdict=data.get("verdict", "PASS"),
            findings=findings,
            confidence=data.get("confidence", 0.5),
            reasoning=data.get("reasoning", ""),
            tokens_used=tokens_used,
            error=error_msg,
        )

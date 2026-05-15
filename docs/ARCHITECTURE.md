# Architecture

This is the short operational map for agents changing Code Review Council. For
the long-form design and roadmap, see `docs/DESIGN.md`.

## Runtime Flow

`pyproject.toml` exposes the CLI as:

```toml
council = "council.cli:app"
```

The main review flow starts in `council/cli.py`:

1. Load config from `.council.toml` via `council/config.py`.
2. Resolve audience and CLI options.
3. Call `council.orchestrator.run_council`.
4. Optionally generate owner presentation.
5. Render terminal, markdown, JSON, HTML, and GitHub PR outputs.
6. Record local history on a best-effort basis.
7. Enforce CI exit behavior.

## Gate Zero

Gate Zero lives in `council/gate_zero.py` with language helpers in
`council/analyzers/`.

It performs deterministic checks before LLM review:

- Secret detection.
- Prompt-injection pattern detection.
- README update checks for new public modules.
- File-size sanity checks.
- Language-specific docs/type checks.
- Configured linters.

Gate Zero can hard-fail before LLM calls when critical deterministic findings
are present.

## Diff Preprocessor

`council/diff_preprocessor.py` filters and budgets diff context.

Responsibilities:

- Respect `.councilignore`.
- Skip generated or low-value files where configured.
- Enforce review token and per-file budgets.
- Surface skipped and truncated files instead of pretending they were reviewed.

Skipped tests, docs, and config files are important context. They must not
become omission-only blockers.

## ReviewPack Assembly

`council/review_pack.py` builds the `ReviewPack` schema from
`council/schemas.py`.

ReviewPack is the canonical input to reviewers and includes:

- Filtered diff text.
- Changed files.
- Changed symbols.
- Diff-local test coverage map.
- Bounded repo-wide test context.
- Gate Zero findings.
- Repo policies.
- Skipped and truncated file metadata.
- Support-file summaries outside the review budget.

Reviewers should reason from ReviewPack, not from raw assumptions about the
repository.

## Reviewer Panel

Reviewer classes live in `council/reviewers/` and share behavior through
`council/reviewers/base.py`.

Default reviewer prompts live in:

- `prompts/secops.md`
- `prompts/qa.md`
- `prompts/architecture.md`
- `prompts/docs.md`

The base reviewer:

- Loads the configured prompt.
- Serializes ReviewPack.
- Delimits untrusted diff content.
- Calls the model through `council/llm_transport.py`.
- Parses reviewer JSON into `ReviewerOutput`.
- Surfaces invalid JSON, malformed findings, timeouts, and exceptions as
  integrity signals.

## Council Chair

`council/chair.py` synthesizes reviewer outputs into `ChairVerdict`.

The Chair must:

- Accept, dismiss, downgrade, or upgrade findings.
- Require evidence for accepted blockers.
- Preserve serious dissent.
- Carry degraded reasons into the final verdict.
- Fail closed if Chair synthesis transport or parsing fails.

Owner output is a presentation layer only. It must translate the same accepted
technical findings and must fall back deterministically if generation fails.

## Reporters

Reporter modules live in `council/reporters/`.

- `terminal.py`: local console output.
- `markdown.py`: developer and owner markdown reports.
- `json_report.py`: machine-readable CI artifact.
- `html_report.py`: standalone HTML report.
- `github_pr.py`: sticky PR summary, annotations, and inline comments.
- `transport.py`: shared transport note helpers.

Reporter changes must preserve parity for verdict, accepted blockers, warnings,
dismissed findings, degraded state, degraded reasons, reviewer errors, and
transport notes where applicable.

## GitHub PR Reporting

GitHub reporting is best-effort output, not verdict computation.

`council/reporters/github_pr.py`:

- Emits workflow annotations.
- Reads GitHub event context safely.
- Posts or updates a sticky PR comment when token and PR context exist.
- Posts deduplicated inline comments for accepted findings with file/line
  evidence.
- Sanitizes untrusted text before embedding it in comments.

GitHub API failures must not change the review verdict.

## Config Loading

`council/config.py` loads `.council.toml` into Pydantic models.

Important config areas:

- `CouncilConfig`
- `EnforcementConfig`
- `GateZeroConfig`
- `ReviewerConfig`
- `ReportersConfig`
- `ContextConfig`
- `HistoryConfig`

Reviewer config supports the canonical `[[reviewers]]` form plus compatibility
forms. Preserve compatibility unless a migration plan says otherwise.

## Degraded Mode And Integrity

Integrity handling spans:

- `council/reviewers/base.py`
- `council/orchestrator.py`
- `council/chair.py`
- `council/reporters/*`

Invalid reviewer JSON, reviewer exceptions, dropped findings, no-evidence fail
outputs, and Chair failures must be visible. See `docs/INTEGRITY_POLICY.md`.

## Tests

Current tests live in a flat `tests/` directory. Add focused tests near existing
coverage:

- Chair behavior: `tests/test_chair_synthesize.py`
- GitHub reporting: `tests/test_github_reporter.py`
- History: `tests/test_history.py`, `tests/test_history_cli.py`
- Transport: `tests/test_llm_transport.py`
- ReviewPack support context: `tests/test_review_pack_support_context.py`
- Prompt support context: `tests/test_support_context_prompts.py`
- Terminal reporting: `tests/test_terminal_reporter.py`

Do not invent `tests/unit/` or `tests/integration/` paths unless a separate
test-layout PR creates them.

## Boundary Rules

- Diff content is untrusted.
- Reviewer output is untrusted.
- Repository config is untrusted.
- GitHub event payloads are untrusted.
- History paths must remain repo-relative when configured.
- No invalid JSON, dropped finding, or reviewer failure may become silent PASS.

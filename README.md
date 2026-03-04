# Code Review Council

Multi-agent LLM code review system — an automated quality gate for AI-generated ("vibe-coded") code.

## How It Works

Changes pass through a pipeline:

1. **Gate Zero** — Fast, deterministic static checks (docstrings, types, secrets, lint). Zero LLM cost.
2. **Diff Preprocessor** — Filters lockfiles, generated code, enforces token budgets.
3. **ReviewPack Assembly** — Builds structured context (symbols, test map, policies) for reviewers.
4. **Reviewer Panel** — Parallel LLM reviewers (SecOps, QA, Architect, Docs) analyze the ReviewPack.
5. **Council Chair** — Synthesizes all findings, accepts/dismisses each with evidence, renders verdict.

Two enforcement modes:
- **Local CLI** (`council review`) — Advisory only, never blocks push.
- **CI** (`council review --ci`) — Hard gate, blocks merge on FAIL.

## Install

```bash
# From source (recommended for alpha)
pip install .

# Or in development mode
pip install -e .
```

## Quick Start

```bash
# Initialize in your repo
cd your-project/
council init

# Set API keys
export ANTHROPIC_API_KEY=sk-...
export OPENAI_API_KEY=sk-...

# Review current changes
council review

# Review staged changes
council review --staged

# CI mode (exits 1 on FAIL)
council review --ci --branch main --output-json council-report.json

# Generate an HTML report for a product owner
council review --audience owner --output-html owner-report.html
```

## Audience Modes

`council review` supports two output audiences. The underlying review engine is identical for both — the same diff, the same reviewers, the same findings. Only the presentation changes.

### `--audience developer` (default)

The standard technical output. Shows:
- Gate Zero static findings
- Reviewer panel results
- Accepted blockers and warnings with file/line references, evidence, and policy IDs
- Chair rationale

This is the default. Existing usage without `--audience` is unchanged.

### `--audience owner`

A plain-English translation of the same findings, aimed at product owners and semi-technical founders who need to understand the review result without reading code.

The owner output:
- **Leads with the recommendation** (SAFE TO MERGE / MERGE WITH CAUTION / FIX BEFORE MERGE)
- Explains what is wrong and why it matters to the product or business
- Provides a copy/paste fix prompt for an AI coding assistant (Claude, Cursor, Lovable, etc.)
- Tells you what to test after the fix
- Flags whether a real engineer should review the fix
- Follows with a technical appendix for developer reference

**Important**: owner mode is a translation layer, not a weaker review. The same analysis engine, the same diff, the same reviewers, the same findings. Only the presentation changes. Serious findings are not hidden or softened.

This is a **PR/diff/code-change review tool**, not a full holistic application audit platform.

### `--output-html <path>`

Writes a standalone, self-contained HTML report (no external assets, no CDN, works offline). Especially useful with `--audience owner` to share a polished, shareable report artifact.

```bash
# Technical HTML for developer review
council review --output-html report.html

# Owner-friendly HTML to share with stakeholders
council review --audience owner --output-html owner-report.html
```

### `--output-md <path>` with audience

The markdown reporter also respects `--audience`. With `--audience owner`, the markdown leads with the recommendation, risk level, plain-English issue cards (including fix prompts), and a technical appendix. Developer audience produces the standard technical markdown.

```bash
council review --audience owner --output-md owner-review.md
```

### Configuring a default audience

Add a `[presentation]` section to `.council.toml`:

```toml
[presentation]
default_audience = "developer"  # or "owner"
```

Absence of this section defaults to `developer`. The CLI `--audience` flag always overrides the config.

## Configuration

`council init` creates `.council.toml` in your repo root and a GitHub Actions workflow. Key settings:

```toml
[council]
chair_model = "openai/gpt-4o"
timeout_seconds = 60
reviewer_concurrency = 2  # throttle parallel reviewer calls to avoid TPM/rate-limit failures

[gate_zero]
require_docs = true
require_type_annotations = true
check_secrets = true

[[reviewers]]
id = "secops"
model = "anthropic/claude-sonnet-4-20250514"
enabled = true

# Optional: set a default output audience
[presentation]
default_audience = "developer"
```

See the solution design document for full configuration reference.

## Architecture

- **Schemas**: Pydantic v2 models enforce structure at every boundary.
- **ReviewPack**: Reviewers get structured context (changed symbols, test coverage map, policy violations), not raw diff text.
- **Evidence-based Chair**: Findings are accepted/dismissed individually with explicit reasoning. No count-based rules.
- **Degraded mode**: If a reviewer times out or returns malformed output, the council continues with reduced confidence and surfaces specific integrity issues.
- **JSON CI triage**: JSON reports include per-reviewer `error` and `integrity_error` so blocked runs are easier to debug in CI logs/artifacts.
- **LiteLLM**: Single interface to call any LLM provider.

## Known Limitations (V1 Alpha)

- **Model compatibility**: V1 uses `response_format={"type": "json_object"}` which is supported by OpenAI and Anthropic models via LiteLLM. Gemini and other providers may not support this parameter. If using non-OpenAI/Anthropic models, test compatibility first. A fallback mechanism is planned.
- **Language support**: Gate Zero analyzers (docstrings, type hints) are implemented for Python only. TypeScript/JavaScript analyzers are disabled by default pending implementation. The diff preprocessor, reviewer panel, and Chair work with any language.
- **Test coverage map**: Only detects test files present in the current diff, not the full repo. The QA reviewer is informed this is a weak signal.
- **Large file handling**: Files exceeding the token budget are truncated, not split at logical boundaries. Truncated files are labeled in the ReviewPack.
- **GitHub API variability**: `--github-pr` supports sticky PR comments and workflow annotations, but still runs in best-effort mode. You can tune retries/timeouts with `COUNCIL_GITHUB_MAX_RETRIES`, `COUNCIL_GITHUB_RETRY_BACKOFF_SECONDS`, and `COUNCIL_GITHUB_HTTP_TIMEOUT` for noisy CI networks.

## License

MIT

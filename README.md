# Code Review Council

Multi-agent LLM code review system — an automated quality gate for AI-generated ("vibe-coded") code.

**Requires Python 3.12+.** See [GETTING_STARTED.md](GETTING_STARTED.md) for a full walkthrough.

## How It Works

Changes pass through a pipeline:

1. **Gate Zero** — Fast, deterministic static checks (docstrings, types, secrets, lint, prompt-injection detection). Zero LLM cost.
2. **Diff Preprocessor** — Filters lockfiles, generated code, enforces token budgets.
3. **ReviewPack Assembly** — Builds structured context (symbols, test map, policies) for reviewers.
4. **Reviewer Panel** — Parallel LLM reviewers (SecOps, QA, Architect, Docs) analyze the ReviewPack.
5. **Council Chair** — Synthesizes all findings, accepts/dismisses each with evidence, renders verdict.

Two enforcement modes:
- **Local CLI** (`council review`) — Advisory only, never blocks push.
- **CI** (`council review --ci`) — Hard gate, blocks merge on FAIL.

Two audience modes:
- **Developer** (default) — Full technical detail with all findings.
- **Owner** (`--audience owner`) — Executive summary with trust signal, top risks, and reviewer health.

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

# Owner audience with HTML report
council review --audience owner --output-html report.html

# Post results to GitHub PR
council review --ci --github-pr --branch main
```

## Configuration

`council init` creates `.council.toml` in your repo root and a GitHub Actions workflow. Key settings:

```toml
[council]
chair_model = "openai/gpt-4o"
timeout_seconds = 60

[gate_zero]
require_docs = true
require_type_annotations = true
check_secrets = true

[[reviewers]]
id = "secops"
model = "anthropic/claude-sonnet-4-20250514"
enabled = true
```

See the solution design document for full configuration reference.

## Architecture

- **Schemas**: Pydantic v2 models enforce structure at every boundary.
- **ReviewPack**: Reviewers get structured context (changed symbols, test coverage map, policy violations), not raw diff text.
- **Evidence-based Chair**: Findings are accepted/dismissed individually with explicit reasoning. No count-based rules.
- **Degraded mode**: If a reviewer times out or returns malformed output, the council continues with reduced confidence and surfaces specific integrity issues.
- **LiteLLM**: Single interface to call any LLM provider.

## Known Limitations (V1 Alpha)

- **Model compatibility**: V1 uses `response_format={"type": "json_object"}` which is supported by OpenAI and Anthropic models via LiteLLM. Gemini and other providers may not support this parameter. If using non-OpenAI/Anthropic models, test compatibility first. A fallback mechanism is planned.
- **Language support**: Gate Zero analyzers (docstrings, type hints) are implemented for Python only. TypeScript/JavaScript analyzers are disabled by default pending implementation. The diff preprocessor, reviewer panel, and Chair work with any language.
- **Test coverage map**: Only detects test files present in the current diff, not the full repo. The QA reviewer is informed this is a weak signal.
- **Large file handling**: Files exceeding the token budget are truncated, not split at logical boundaries. Truncated files are labeled in the ReviewPack.
- **GitHub PR reporter**: Posts a sticky summary comment and emits workflow annotations. Inline file-level comments are not yet implemented.

## License

MIT

# 🏛️ Code Review Council

> **AI reviews AI-generated code** — a multi-agent quality gate for the era where bots write PRs and humans are the trust layer.
> 
> Designed for **agentic codebases** where AI writes most of the diff — the review loop is automated, auditable, and observable end-to-end.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![GitHub Actions](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=github-actions&logoColor=white)](https://github.com/vishal8shah/code-review-council/actions)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://makeapullrequest.com)
[![Docs](https://img.shields.io/badge/docs-live-orange)](https://vishal8shah.github.io/code-review-council/)

---

## 🚀 What Is This?

You're shipping AI-generated code faster than any human can review it line-by-line. **Code Review Council** is the automated trust layer that fills that gap.

Every time a PR is opened, a panel of specialist AI reviewers fires in parallel — Security, QA, Architecture, Docs — and a Council Chair synthesises the findings into one structured verdict. Posted directly on your GitHub PR. In under 60 seconds.

**Think of it as**: a senior engineering panel that reviews every PR, at 2am, without complaining, without skimming.

---

## 🔬 How It Works

Changes pass through a five-stage pipeline:

| Stage | Name | What It Does | LLM Cost |
|-------|------|-------------|----------|
| 0 | **Gate Zero** | Fast deterministic checks — secrets, lint, types, missing docs. Under 2 seconds. | Zero |
| 1 | **Diff Preprocessor** | Filters lockfiles, generated code, enforces token budgets | Zero |
| 2 | **ReviewPack Assembly** | Builds structured context: changed symbols, test coverage map, policy violations | Zero |
| 3 | **Reviewer Panel** | SecOps, QA, Architect, Docs — parallel LLM agents, evidence required | 4× LLM calls |
| 4 | **Council Chair** | Synthesises all findings, requires full exploit chain for blockers, renders verdict | 1× LLM call |

**Verdict options:** `PASS` · `PASS WITH WARNINGS` · `FAIL`

Two enforcement modes:
- 💻 **Local CLI** (`council review`) — Advisory only, never blocks push.
- 🚨 **CI** (`council review --ci`) — Hard gate, blocks merge on FAIL.

---

## ⚡ Install

```bash
# From source (recommended for alpha)
pip install .

# Or in development mode
pip install -e .
```

---

## 🏃 Quick Start

```bash
# Initialise in your repo
cd your-project/
council init

# Set API keys
export ANTHROPIC_API_KEY=sk-...
export OPENAI_API_KEY=sk-...

# Preflight setup and model compatibility
council doctor --branch main

# Review current changes
council review

# Review staged changes
council review --staged

# CI mode (exits 1 on FAIL)
council review --ci --branch main --output-json council-report.json

# Generate an HTML report for a product owner
council review --audience owner --output-html owner-report.html
```

---

## 🎯 Audience Modes

`council review` supports two output audiences. The underlying review engine is identical for both — the same diff, the same reviewers, the same findings. Only the presentation changes.

### 🧑‍💻 `--audience developer` (default)

The standard technical output. Shows:
- Gate Zero static findings
- Reviewer panel results
- Accepted blockers and warnings with file/line references, evidence, and policy IDs
- Chair rationale

This is the default. Existing usage without `--audience` is unchanged.

### 🧑‍💼 `--audience owner`

A plain-English translation of the same findings, aimed at product owners and semi-technical founders who need to understand the review result without reading code.

The owner output:
- **Leads with the recommendation** (SAFE TO MERGE / MERGE WITH CAUTION / FIX BEFORE MERGE)
- Explains what is wrong and why it matters to the product or business
- Provides a copy/paste fix prompt for an AI coding assistant (Claude, Cursor, Lovable, etc.)
- Tells you what to test after the fix
- Flags whether a real engineer should review the fix
- Follows with a technical appendix for developer reference

> ⚠️ **Important**: owner mode is a translation layer, not a weaker review. The same analysis engine, the same diff, the same reviewers, the same findings. Serious findings are never hidden or softened.

This is a **PR/diff/code-change review tool**, not a full holistic application audit platform.

### 📄 `--output-html <path>`

Writes a standalone, self-contained HTML report (no external assets, no CDN, works offline). Especially useful with `--audience owner` to share a polished, shareable report artifact.

```bash
# Technical HTML for developer review
council review --output-html report.html

# Owner-friendly HTML to share with stakeholders
council review --audience owner --output-html owner-report.html
```

### 📄 `--output-md <path>` with audience

The markdown reporter also respects `--audience`. With `--audience owner`, the markdown leads with the recommendation, risk level, plain-English issue cards (including fix prompts), and a technical appendix. Developer audience produces the standard technical markdown.

```bash
council review --audience owner --output-md owner-review.md
```

### ⚙️ Configuring a default audience

Add a `[presentation]` section to `.council.toml`:

```toml
[presentation]
default_audience = "developer"  # or "owner"
```

Absence of this section defaults to `developer`. The CLI `--audience` flag always overrides the config.

---

## 🛡️ What Makes It Different

### Unlike basic LLM code review:
- ❌ Pattern-matched security alerts with no exploit chain
- ✅ Requires full exploitability proof before accepting a blocker

### Unlike "just run the linter":
- ❌ No semantic understanding of what changed and why
- ✅ Reviewers get structured context — symbols, test map, policies — not raw diff text

### Unlike human review at scale:
- ❌ Senior engineers as bottleneck, rubber-stamping at 11pm
- ✅ Parallel specialist agents, consistent quality, every PR, every time

---

## 🔁 The Autonomous Loop

```
AI agent writes code
        ↓
   PR opened
        ↓
Council reviews (< 60s)
        ↓
  PASS? → merge ✅
  FAIL? → findings fed back to coding agent
        ↓
  Agent patches + resubmits
        ↓
   Council re-reviews
        ↓
 (repeat until PASS)
```

Built to support **OpenClaw** and similar multi-bot frameworks — where the writer and the reviewer work in the same automated loop.

---

## ⚙️ Configuration

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
name = "Security Operations Reviewer"
model = "openai/gpt-5.2"
prompt = "prompts/secops.md"
enabled = true

# Optional: set a default output audience
[presentation]
default_audience = "developer"
```

Model schema note: canonical reviewer config is `[[reviewers]]`, and nested forms `[[council.reviewer]]` / `[[council.reviewers]]` are also accepted for compatibility.

### 🧠 Model Presets

**Balanced preset:**
```toml
[council]
chair_model = "anthropic/claude-sonnet-4-6"

[[reviewers]]
id = "secops"
name = "Security Operations Reviewer"
model = "openai/gpt-5.2"
prompt = "prompts/secops.md"

[[reviewers]]
id = "qa"
name = "QA Engineer"
model = "openai/gpt-5.2"
prompt = "prompts/qa.md"

[[reviewers]]
id = "architect"
name = "Solutions Architect"
model = "openai/gpt-4o"
prompt = "prompts/architecture.md"

[[reviewers]]
id = "docs"
name = "Documentation Reviewer"
model = "openai/gpt-4o-mini"
prompt = "prompts/docs.md"
```

**Simple ops preset:**
```toml
[council]
chair_model = "openai/gpt-4o"

[[reviewers]]
id = "secops"
name = "Security Operations Reviewer"
model = "openai/gpt-5.2"
prompt = "prompts/secops.md"

[[reviewers]]
id = "qa"
name = "QA Engineer"
model = "openai/gpt-5.2"
prompt = "prompts/qa.md"

[[reviewers]]
id = "architect"
name = "Solutions Architect"
model = "openai/gpt-4o"
prompt = "prompts/architecture.md"

[[reviewers]]
id = "docs"
name = "Documentation Reviewer"
model = "openai/gpt-4o-mini"
prompt = "prompts/docs.md"
```

> 🔑 **BYOK note**: fork PRs can run the `council-byok` workflow to produce `council-report.json` and `council-review.md` artifacts even when upstream secrets are unavailable.

---

## 🏗️ Architecture

- **Schemas**: Pydantic v2 models enforce structure at every boundary.
- **ReviewPack**: Reviewers get structured context (changed symbols, test coverage map, policy violations), not raw diff text.
- **Evidence-based Chair**: Findings are accepted/dismissed individually with explicit reasoning. No count-based rules.
- **Degraded mode**: If a reviewer times out or returns malformed output, the council continues with reduced confidence and surfaces specific integrity issues.
- **JSON CI triage**: JSON reports include per-reviewer `error` and `integrity_error` so blocked runs are easier to debug in CI logs/artifacts.
- **LiteLLM**: Single interface to call any LLM provider.

---

## 📊 Verdict Example

```
Overall verdict: PASS  (confidence: 0.90)

Accepted warnings:
  [LOW] site/docs/stylesheets/extra.css:1
        No tests present for CSS assets — expected for docs-only changes.
  [LOW] .github/workflows/pages.yml:1
        Validation gate may surprise fork contributors if images not committed.

Reviewer panel:
  secops     PASS   0 findings
  qa         PASS   2 findings
  architect  PASS   0 findings
  docs       PASS   0 findings

Runtime: 48s
```

---

## 📚 Docs Site

Project docs are published via the GitHub Pages workflow.

👉 **[vishal8shah.github.io/code-review-council](https://vishal8shah.github.io/code-review-council/)**

```bash
# Local docs preview
pip install -r site/requirements-docs.txt
mkdocs serve -f site/mkdocs.yml
```

Add your infographic PNGs under `site/docs/assets/infographics/`. If you fork, update `site_url` in `site/mkdocs.yml`.

---

## ⚠️ Known Limitations (V1 Alpha)

- **Model compatibility**: Council now retries without `response_format={"type": "json_object"}` when a provider/model rejects native JSON mode. That improves portability, but some providers still return malformed JSON or require prompt tuning. Council surfaces `output_mode` and transport notes when fallback transport is used or fails.
- **Language support**: Gate Zero analyzers now cover Python, TypeScript, and JavaScript. ReviewPack symbol extraction also covers Python plus parser-free TypeScript/JavaScript exports, including default exports, interfaces, and type aliases. TypeScript/JavaScript analyzers remain disabled by default until explicitly enabled in `[gate_zero.analyzers]`. The diff preprocessor, reviewer panel, and Chair work with any language.
- **Test coverage map**: Only detects test files present in the current diff, not the full repo. Python test matching uses import analysis, while TypeScript/JavaScript coverage uses relative-import and filename heuristics only. Files that stay in the filtered PR diff but fall outside the token budget still contribute to ReviewPack metadata and diff-local coverage hints.
- **Large file handling**: Reviewers still see a budgeted/truncated diff, not logical parser-aware chunks. Files or hunks excluded by token budget are surfaced in ReviewPack metadata so skipped tests/docs/config still remain visible to reviewers as changed support context.
- **GitHub API variability**: `--github-pr` now supports sticky PR summaries, workflow annotations, and best-effort inline PR comments for accepted findings with file/line evidence. GitHub auth, rate limits, or API failures degrade reporting only; they do not invalidate the review itself. You can tune retries/timeouts with `COUNCIL_GITHUB_MAX_RETRIES`, `COUNCIL_GITHUB_RETRY_BACKOFF_SECONDS`, and `COUNCIL_GITHUB_HTTP_TIMEOUT` for noisy CI networks.

---

## 🗺️ Roadmap

- [x] V1 — GitHub Actions CI gate, 4 reviewers, 2 output modes, BYOK for forks
- [x] V2 — Python/TypeScript/JavaScript ReviewPack parity and shared test-path logic
- [x] V3 — JSON transport fallback, `council doctor`, sticky + inline GitHub PR reporting
- [ ] V4 — Friendlier onboarding, stronger fix guidance, full-repo context expansion, and safer self-serve defaults

---

## 🤝 Contributing

1. Fork the repo
2. `pip install -e .` for dev mode
3. Run `pytest` — all tests must pass
4. Open a PR — Council will review it automatically ✅

BYOK note: fork PRs can run the `council-byok` workflow to produce `council-report.json` and `council-review.md` artifacts even when upstream secrets are unavailable. See the solution design document for full configuration reference.

---

## 📜 License

MIT — use freely, commercially or personally.

---

<div align="center">

**🏛️ Code Review Council — Verify the AI. With another AI. With evidence.**

[⭐ Star this repo](https://github.com/vishal8shah/code-review-council) · [🍴 Fork it](https://github.com/vishal8shah/code-review-council/fork) · [📖 Read the docs](https://vishal8shah.github.io/code-review-council/) · [🐛 Report an issue](https://github.com/vishal8shah/code-review-council/issues)

Built at 2am. Reviewed by itself. Shipped anyway. 😅

</div>

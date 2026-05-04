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

Every time a PR is opened, a panel of specialist AI reviewers fires — Security, QA, Architecture, Docs — and a Council Chair synthesises the findings into one structured verdict. Posted directly on your GitHub PR, with latency controlled by model choice, diff size, and reviewer concurrency.

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

# Set the key for the models you plan to run.
# The generated GitHub workflows are currently pinned to Gemini:
export GOOGLE_API_KEY=...

# Optional: set these only if your local .council.toml uses them.
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

`council init` now ends with recommended setup commands, and `council doctor`
prints the active review profile plus recommended next steps before you spend
money on a full model run.

---

## 🎯 Audience Modes

`council review` supports two output audiences. The underlying review engine is identical for both — the same diff, the same reviewers, the same findings. Only the presentation changes.

### 🧑‍💻 `--audience developer` (default)

The standard technical output. Shows:
- Gate Zero static findings
- Reviewer panel results
- Accepted blockers and warnings with file/line references, evidence, and policy IDs
- Deterministic next steps, fix prompts, and verification guidance for accepted findings
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
Council reviews
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
chair_model = "openai/gpt-4o"      # local scaffold default; change per provider/key budget
timeout_seconds = 60               # Chair / owner-summary timeout
reviewer_timeout_seconds = 60      # per-reviewer timeout
reviewer_concurrency = 2           # throttle parallel reviewer calls to avoid TPM/rate-limit failures

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

# Optional bounded full-repo test discovery. This helps Council see existing
# tests outside the diff without treating the scan as full coverage proof.
[context]
full_repo_tests = true
max_test_files = 500
max_test_file_bytes = 20000

# Optional local review history. Defaults store metadata in the OS user cache,
# not the repo, and do not persist raw diff/model text.
[history]
enabled = true
# Leave empty for the OS user-cache database.
# Custom paths must be repo-relative and stay inside the repo.
path = ""
retention_days = 180
store_finding_text = false
```

Leave `history.path` empty for the OS user-cache database. If you set it, use a
repo-relative path only; absolute paths and `..` traversal outside the repo are
rejected because `.council.toml` can be committed by untrusted repositories.

Model schema note: canonical reviewer config is `[[reviewers]]`, and nested forms `[[council.reviewer]]` / `[[council.reviewers]]` are also accepted for compatibility.

### 🧠 Model Presets

The local `.council.toml` scaffold remains provider-configurable. The GitHub
Actions workflows generated by `council init` are pinned to Gemini and write a
temporary CI config using `gemini/gemini-3-pro-preview`,
`reviewer_timeout_seconds = 360`, and `reviewer_concurrency = 1`.

For TS/JS repos that should use Council as a required GitHub PR gate without
vendoring this repo, use the generated `council-openai-gate.yml` workflow. It
installs Council from GitHub, fails closed if `OPENAI_API_KEY` is missing, and
uses `openai/gpt-5.5` with `chair_reasoning_effort = "medium"` for Chair
synthesis. Generate only that workflow with
`council init --workflow-profile openai-gate`. The scaffold pins
`COUNCIL_INSTALL_SPEC` to `v0.2.0`; keep it pinned to a release tag or commit
SHA before enabling required branch protection broadly.

**OpenAI required-gate preset:**
```toml
[council]
chair_model = "openai/gpt-5.5"
chair_reasoning_effort = "medium"
timeout_seconds = 360
reviewer_timeout_seconds = 240
reviewer_concurrency = 2

[gate_zero.analyzers]
python = true
typescript = true
javascript = true
```

**Gemini CI/local parity preset:**
```toml
[council]
chair_model = "gemini/gemini-3-pro-preview"
timeout_seconds = 360
reviewer_timeout_seconds = 360
reviewer_concurrency = 1

[[reviewers]]
id = "secops"
name = "Security Operations Reviewer"
model = "gemini/gemini-3-pro-preview"
prompt = "prompts/secops.md"

[[reviewers]]
id = "qa"
name = "QA Engineer"
model = "gemini/gemini-3-pro-preview"
prompt = "prompts/qa.md"

[[reviewers]]
id = "architect"
name = "Solutions Architect"
model = "gemini/gemini-3-pro-preview"
prompt = "prompts/architecture.md"

[[reviewers]]
id = "docs"
name = "Documentation Reviewer"
model = "gemini/gemini-3-pro-preview"
prompt = "prompts/docs.md"
```

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
- **Deterministic guidance**: Reports add copy/paste fix prompts, verification steps, and review next steps without making another model call.
- **Degraded mode**: If a reviewer times out or returns malformed output, the council continues with reduced confidence and surfaces specific integrity issues, including sanitized schema field/type diagnostics for dropped findings.
- **JSON CI triage**: JSON reports include per-reviewer `error` and `integrity_error` so blocked runs are easier to debug in CI logs/artifacts.
- **LiteLLM**: Single interface to call any LLM provider.
- **Local history**: V4B records privacy-preserving run metadata and repeated-debt signals without storing raw diffs or model-generated finding text by default.
- **Bounded repo test context**: V4C scans existing repo test files within configured caps so reviewers can distinguish "tests outside the diff" from "no tests found."

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
- **Language support**: Gate Zero analyzers cover Python, TypeScript, and JavaScript by default. Python uses AST-based checks; TypeScript and JavaScript use parser-free deterministic heuristics for exports, docs, and type-presence signals. Go, Rust, Java, Ruby, and other languages still receive LLM diff review, but do not yet have dedicated deterministic analyzers. Council does not replace ESLint, `tsc`, compilers, type-aware static analyzers, or language-native tests.
- **Test context**: `test_coverage_map` remains diff-local. V4C also adds bounded repo-wide test context that respects `.councilignore`, skips heavy directories, and is capped by `[context]`; it reduces false missing-test findings but is not a proof of test quality or complete coverage.
- **Large file handling**: Reviewers still see a budgeted/truncated diff, not logical parser-aware chunks. Files or hunks excluded by token budget are surfaced in ReviewPack metadata so skipped tests/docs/config still remain visible to reviewers as changed support context.
- **GitHub API variability**: `--github-pr` now supports sticky PR summaries, workflow annotations, and best-effort inline PR comments for accepted findings with file/line evidence. GitHub auth, rate limits, or API failures degrade reporting only; they do not invalidate the review itself. You can tune retries/timeouts with `COUNCIL_GITHUB_MAX_RETRIES`, `COUNCIL_GITHUB_RETRY_BACKOFF_SECONDS`, and `COUNCIL_GITHUB_HTTP_TIMEOUT` for noisy CI networks.

---

## 🗺️ Roadmap

- [x] V1 — GitHub Actions CI gate, 4 reviewers, 2 output modes, BYOK for forks
- [x] V2 — Python/TypeScript/JavaScript ReviewPack parity and shared test-path logic
- [x] V3 — JSON transport fallback, `council doctor`, sticky + inline GitHub PR reporting
- [x] V4A — Delivered friendlier onboarding, stronger fix guidance, Gemini CI docs, and safer self-serve defaults
- [x] V4B first slice — Delivered local review history, privacy-preserving repeated-debt signals, and trend summaries; autofix remains deferred
- [x] V4C — Delivered bounded full-repo test context for changed source files; full semantic indexing and autofix remain deferred
- [x] V4D — Graduated TypeScript and JavaScript Gate Zero analyzers to default-on with per-language opt-out
- [x] V4E — Added a multi-repo OpenAI PR-gate workflow with GPT-5.5 medium-reasoning Chair support

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

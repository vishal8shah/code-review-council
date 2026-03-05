# 🏛️ Code Review Council

> **AI reviews AI-generated code** — a multi-agent quality gate for the era where bots write PRs and humans are the trust layer.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![GitHub Actions](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=github-actions&logoColor=white)](https://github.com/vishal8shah/code-review-council/actions)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://makeapullrequest.com)
[![Docs](https://img.shields.io/badge/docs-live-orange)](https://vishal8shah.github.io/code-review-council/)

---

## 🚀 What Is This?

You're shipping AI-generated code faster than any human can review it line-by-line. **Code Review Council** is the automated trust layer that fills that gap.

Every time a PR is opened, a panel of specialist AI reviewers fires in parallel — Security, QA, Architecture, Docs — and a Council Chair synthesises the findings into one structured verdict. Posted directly on your GitHub PR. In under 60 seconds.

**Think of it as**: a senior engineering panel that reviews every PR, at 2am, without complaining, without skimming.

---

## ⚡ Quick Start

```bash
# Install
pip install .

# Initialise in your repo (creates .council.toml + GitHub Actions workflow)
cd your-project/
council init

# Set your API key(s)
export ANTHROPIC_API_KEY=sk-...
export OPENAI_API_KEY=sk-...

# Run a review
council review

# CI mode — exits 1 on FAIL, blocks merge
council review --ci --branch main --output-json council-report.json
```

---

## 🔬 The Pipeline

Every PR passes through five stages:

| Stage | Name | What It Does | LLM Cost |
|-------|------|-------------|----------|
| 0 | **Gate Zero** | Deterministic checks — secrets, lint, types, missing docs | Zero |
| 1 | **Diff Preprocessor** | Strips lockfiles, generated code, enforces token budgets | Zero |
| 2 | **ReviewPack** | Builds structured context: changed symbols, test map, policy violations | Zero |
| 3 | **Reviewer Panel** | SecOps, QA, Architect, Docs — parallel, evidence-required | 4× LLM calls |
| 4 | **Council Chair** | Synthesises findings, requires exploit chain for blockers, renders verdict | 1× LLM call |

**Verdict options:** `PASS` · `PASS WITH WARNINGS` · `FAIL`

---

## 🎯 Two Output Modes

Same analysis engine. Same diff. Same reviewers. Two audiences.

| Mode | Audience | What You Get |
|------|----------|--------------|
| 🧑‍💻 **Developer** (default) | Engineers | File/line findings, evidence chains, fix suggestions, policy IDs |
| 🧑‍💼 **Owner** | Product / Leadership | Plain-English risk summary, ship/no-ship recommendation, copy-paste fix prompt for your AI coding agent |

```bash
# Developer report (default)
council review

# Owner report — plain English, shareable HTML
council review --audience owner --output-html owner-report.html
```

> ⚠️ Owner mode is a **translation layer, not a weaker review**. Serious findings are never hidden or softened.

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

## ⚙️ Configuration

`council init` generates `.council.toml` in your repo root:

```toml
[council]
chair_model = "anthropic/claude-sonnet-4-6"
timeout_seconds = 60
reviewer_concurrency = 2

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

[presentation]
default_audience = "developer"  # or "owner"
```

---

## 🗺️ Roadmap

- [x] V1 — GitHub Actions CI gate, 4 reviewers, 2 output modes, BYOK for forks
- [ ] V2 — PR inline annotations, team dashboard, MCP server for agent self-review
- [ ] V3 — Auto-fix generation: Council flags → agent patches → Council re-reviews → merge

---

## ⚠️ Known Limitations (V1 Alpha)

- **Language support**: Gate Zero static analyzers are Python-only. Reviewer panel + Chair work with any language.
- **Model compatibility**: Uses `response_format={"type": "json_object"}` — supported by OpenAI and Anthropic via LiteLLM. Test Gemini/other providers first.
- **Test coverage map**: Detects test files in the current diff only, not the full repo.
- **Large files**: Files over token budget are truncated (not split at logical boundaries).

---

## 📖 Docs

Full documentation, getting started guide, and workflow reference:

👉 **[vishal8shah.github.io/code-review-council](https://vishal8shah.github.io/code-review-council/)**

```bash
# Local docs preview
pip install -r site/requirements-docs.txt
mkdocs serve -f site/mkdocs.yml
```

---

## 🤝 Contributing

1. Fork the repo
2. `pip install -e .` for dev mode
3. Run `pytest` — all tests must pass
4. Open a PR — Council will review it automatically ✅

BYOK note: fork PRs can run the `council-byok` workflow to produce artifacts even when upstream secrets are unavailable.

---

## 📜 License

MIT — use freely, commercially or personally.

---

<div align="center">

**🏛️ Code Review Council — Verify the AI. With another AI. With evidence.**

[⭐ Star this repo](https://github.com/vishal8shah/code-review-council) · [🍴 Fork it](https://github.com/vishal8shah/code-review-council/fork) · [📖 Read the docs](https://vishal8shah.github.io/code-review-council/) · [🐛 Report an issue](https://github.com/vishal8shah/code-review-council/issues)

Built at 2am. Reviewed by itself. Shipped anyway. 😅

</div>

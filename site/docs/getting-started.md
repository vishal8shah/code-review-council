# 🚀 Getting Started

> You can have Council running locally in under 5 minutes. CI integration takes another 10. This page walks through both.

---

## 📋 Prerequisites

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| Python | 3.12+ | Current development and CI run on 3.13; use 3.12+ locally |
| Git | Any recent | Used for diff extraction |
| API key | At least one | OpenAI, Anthropic, or Google |
| GitHub Actions | Optional | Required for CI gate only |

---

## 📦 Install

### From source (recommended while in active development)

```bash
git clone https://github.com/vishal8shah/code-review-council
cd code-review-council
pip install .
```

### Development install (editable — for contributors)

```bash
pip install -e .
```

Verify the install:

```bash
council --version
```

---

## ⚙️ Initialize

Run this inside the repository you want to review:

```bash
council init
```

This creates the review config, ignore file, default prompts, and workflows:

| File | Purpose |
|------|---------|
| `.council.toml` | Your reviewer config, model assignments, token budgets, policy rules |
| `.councilignore` | Review-scope exclusions for lockfiles, generated output, vendored files, and similar noise |
| `prompts/*.md` | Default persona prompts referenced by `.council.toml` |
| `.github/workflows/council-*.yml` | CI workflow scaffolding (PR gate + BYOK variants) |

!!! tip "Check `.council.toml` before your first review"
    The defaults are sensible, but you'll want to confirm the `chair_model` and reviewer model assignments match your available keys. The generated `.council.toml` includes the current user-facing options inline. Run `council doctor --branch main` before the first real review to see the active review profile and the next recommended command.

---

## 🔑 Set Your API Keys (BYOK)

Council is bring-your-own-key. The generated GitHub workflows are pinned to
Gemini, so `GOOGLE_API_KEY` is required for the default CI path. Set other keys
only if your local `.council.toml` uses those providers.

```bash
export GOOGLE_API_KEY=...
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
```

!!! warning "Use restricted keys"
    Create API keys with **minimal scopes** — inference only, no billing access, no admin. See [Security → API Key Hardening](security.md#api-key-hardening) for per-provider recommendations.

For GitHub Actions, store these as **repository secrets** (not environment variables):

```
Settings → Secrets and variables → Actions → New repository secret
```

---

## 💻 Run Locally

### Basic review against your current branch

```bash
council review --branch main
```

### Advisory mode — output only, never blocks

```bash
council review --branch main --output-md council-review.md
```

### CI mode — exits non-zero on FAIL

```bash
council review --ci --branch main --output-json council-report.json
```

### Save both formats at once

```bash
council review --ci --branch main \
  --output-json council-report.json \
  --output-md council-review.md
```

!!! info "First run tip"
    The first run fetches model responses — expect anything from under a minute to several minutes depending on diff size, model choice, and reviewer concurrency. Preview models can be slower, which is why generated CI sets explicit reviewer timeouts.

---

## 📤 Output Artifacts

| Artifact | Format | How to get it |
|----------|--------|---------------|
| `council-report.json` | JSON | `--output-json <path>` |
| `council-review.md` | Markdown | `--output-md <path>` |
| GitHub Actions artifact | Both | Auto-uploaded in CI workflows |

The JSON report includes the full `ChairVerdict` — per-reviewer findings, confidence scores, `degraded_reasons` if any reviewer failed, and the final `PASS` / `FAIL` / `PASS WITH WARNINGS` verdict. Markdown, HTML, terminal, and PR summaries also include deterministic next steps; accepted findings include copy/paste fix prompts and verification guidance.

---

## Local Review History

Phase 4B adds a local history summary for trends across runs:

```bash
council history summary --days 30 --limit 10
```

History defaults to an OS-cache SQLite database, not a repo file. With
`store_finding_text = false`, Council stores fingerprints and classification
fields only; it does not store raw diffs, evidence, suggestions, fix prompts,
Chair reasoning, or model-generated finding descriptions. `[DEBT]` is shown
only when the same fingerprint appears in three consecutive review runs.

---

## 🔧 CI Setup (GitHub Actions)

After `council init`, two workflow files are scaffolded:

| Workflow | Trigger | Use Case |
|----------|---------|----------|
| `council-review.yml` | `pull_request` | Automatic review on every PR from your own branches |
| `council-byok.yml` | `workflow_dispatch` | Manual review for fork PRs, specific branches, or external contributors |

Both generated workflows write a temporary Gemini config in CI using
`gemini/gemini-3-pro-preview`, `reviewer_timeout_seconds = 360`, and
`reviewer_concurrency = 1`.

### Add your secrets, then push:

```bash
git add .github/workflows/
git commit -m "ci: add Council review workflows"
git push
```

Council will automatically review the next PR opened against your default branch.

!!! danger "Fork PRs and secrets"
    Fork PRs cannot access repository secrets (GitHub's security model). `council-review.yml` detects this and skips the LLM step, uploading a report that explains the skip. For fork contributor PRs, use `council-byok.yml` with `workflow_dispatch` and a fork-local `GOOGLE_API_KEY` instead.

---

## 🛠️ Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `council: command not found` | Not installed in active virtualenv | `pip install .` in the repo root |
| Empty diff / 0 findings on all reviewers | Missing `--branch` flag in `--ci` mode | Add `--branch main` (or your base branch) |
| Reviewer timeouts | Model API slow or rate-limited | Increase `reviewer_timeout_seconds` in `.council.toml` |
| `GOOGLE_API_KEY not found` | Gemini-pinned workflow has no key | Add `GOOGLE_API_KEY` in `Settings → Secrets` or export it locally |
| Fork PR review skipped | Expected — not a bug | Use `council-byok.yml` for fork contributors |
| `integrity_error` in JSON report | A reviewer returned unparseable output | Run `council doctor --branch main`; some models use prompt-only JSON fallback and Council now reports that transport mode explicitly |

---

## ⏩ Next Steps

- [Overview](overview.md) — understand the full pipeline and multi-LLM design
- [Security](security.md) — key scoping, threat model, merge gates
- [Design](design.md) — how the Chair adjudicates findings and avoids speculative blocks
- [Self Review](self-review.md) — see real output from Council reviewing its own PR

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

Example output:

```text
Council history summary for code-review-council
Runs: 12 in the last 30 day(s)
Degraded runs: 1
Verdicts: FAIL=3, PASS=7, PASS_WITH_WARNINGS=2
Severity counts: CRITICAL=2, HIGH=8, MEDIUM=14
Category counts: security=4, testing=10, architecture=6, documentation=4
Repeated fingerprints:
  [DEBT]   HIGH/security council/history.py fingerprint=a3f2c1b4d5e6 seen=4, consecutive=4, reviewer=secops
  [REPEAT] MEDIUM/testing council/cli.py fingerprint=9f1e2d3c4b5a seen=2, consecutive=2, reviewer=qa
History database: C:\Users\you\AppData\Local\code-review-council\history.sqlite
```

History defaults to an OS-cache SQLite database, not a repo file. With
`store_finding_text = false`, Council stores fingerprints and classification
fields only; it does not store raw diffs, evidence, suggestions, fix prompts,
Chair reasoning, or model-generated finding descriptions. `[DEBT]` is shown
only when the same fingerprint appears in three consecutive review runs.
If `history.path` is set, it must be relative to the repo and stay inside it;
absolute paths, `~` escapes, and parent traversal are rejected.

If history inspection cannot complete because the database is unavailable,
corrupt, or has a newer unsupported schema, `council history summary` exits
non-zero with a concise error. Review runs remain best-effort for history
writes and do not change verdicts when local history cannot be recorded.

## Bounded Repo Test Context

Phase 4C scans existing repo test files for changed source files so QA reviewers
can distinguish tests outside the diff from no tests found. The scan is bounded,
respects `.councilignore`, skips heavy directories such as `.git`,
`node_modules`, build/cache folders, and virtual environments, and does not
prove test quality or complete coverage.

```toml
[context]
full_repo_tests = true
max_test_files = 500
max_test_file_bytes = 20000
```

If the scan hits a cap or cannot read a test file, Council keeps the review
non-blocking and labels the repo-wide test context as incomplete.

## Language Analyzers

Gate Zero enables Python, TypeScript, and JavaScript analyzers by default.
Python uses stdlib AST parsing; TypeScript and JavaScript use dependency-free
export heuristics for documentation/type-presence checks. If a project needs a
softer rollout, disable a language explicitly:

```toml
[gate_zero.analyzers]
python = true
typescript = false
javascript = false
```

---

## 🔧 CI Setup (GitHub Actions)

After `council init`, three workflow files are scaffolded:

| Workflow | Trigger | Use Case |
|----------|---------|----------|
| `council-review.yml` | `pull_request` | Automatic review on every PR from your own branches |
| `council-byok.yml` | `workflow_dispatch` | Manual review for fork PRs, specific branches, or external contributors |
| `council-openai-gate.yml` | `pull_request` | Required PR gate for other repos using `OPENAI_API_KEY` |

The Gemini workflows write a temporary Gemini config in CI using
`gemini/gemini-3-pro-preview`, `reviewer_timeout_seconds = 360`, and
`reviewer_concurrency = 1`.

`council-openai-gate.yml` is the multi-repo deployment template. It installs
Council from GitHub, fails closed if `OPENAI_API_KEY` is missing, and uses
`openai/gpt-5.5` with `chair_reasoning_effort = "medium"` for Chair synthesis.
The scaffold pins `COUNCIL_INSTALL_SPEC` to `v0.2.0` by default. Keep it pinned
to a release tag or commit SHA before making it a protected-branch requirement
across many repos.

For external repos that only need the OpenAI gate workflow, run:

```bash
council init --workflow-profile openai-gate
```

See the [Adoption Guide](adoption-guide.md) before enabling branch protection.

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
| `integrity_error` in JSON report | A reviewer timed out, returned unparseable JSON, or emitted malformed finding objects | Run `council doctor --branch main`; inspect the per-reviewer `error` for sanitized schema field/type details and transport mode |

---

## ⏩ Next Steps

- [Overview](overview.md) — understand the full pipeline and multi-LLM design
- [Security](security.md) — key scoping, threat model, merge gates
- [Design](design.md) — how the Chair adjudicates findings and avoids speculative blocks
- [Self Review](self-review.md) — see real output from Council reviewing its own PR

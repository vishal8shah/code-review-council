# ⚙️ Workflows

> Council ships with two GitHub Actions workflows. Which one you use depends on who opened the PR and whether secrets are available.

---

## 🔀 Quick Decision Guide

```
Who opened the PR?
        │
   ┌────┴──────┐
   │              │
 You / your team   External / fork contributor
   │              │
   ▼              ▼
council-review.yml    council-byok.yml
(auto, on PR open)    (manual, workflow_dispatch)
```

---

## 📊 Side-by-Side Comparison

| | `council-review.yml` | `council-byok.yml` |
|---|---|---|
| **Trigger** | `pull_request` (automatic) | `workflow_dispatch` (manual) |
| **Secrets access** | Repository secrets only | Repository secrets (you supply them) |
| **Fork PRs** | ⚠️ Skips LLM step (no secrets) | ✅ Full review (you trigger it) |
| **Inputs** | None — runs on the PR branch | `base_ref`, `upstream_repo`, `audience` |
| **Input validation** | N/A | ✅ Branch ref + repo format validated |
| **Artifacts** | `council-report.json` | `council-report.json` + `council-review.md` |
| **Use case** | Every PR from your own branches | Fork PRs, external contributors, targeted re-runs |

---

## 🔄 PR Workflow — `council-review.yml`

This is the always-on review gate. It fires automatically when a PR is opened or updated.

### What it does

1. Checks out the PR branch
2. Runs Gate Zero (deterministic checks)
3. If LLM secrets are available: runs the full 5-stage pipeline
4. If secrets are unavailable (fork PR): skips LLM, uploads a report explaining the skip
5. Uploads `council-report.json` as a workflow artifact

### Where to find the artifact

```
Actions tab → [workflow run] → Artifacts → council-report
```

!!! danger "Fork PRs"
    Fork PRs cannot access repository secrets — this is GitHub's security model, not a Council bug. The PR workflow detects this, skips the LLM step, and uploads a `council-report.json` with a `fork_pr_skip` explanation. **Do not work around this.** Use `council-byok.yml` to review fork contributor PRs.

---

## 🔑 BYOK Workflow — `council-byok.yml`

This is the manual, key-controlled review workflow. You trigger it explicitly from the Actions tab.

### Workflow dispatch inputs

| Input | Required | Description |
|-------|----------|-------------|
| `base_ref` | ✅ Yes | The base branch to diff against (e.g. `main`) |
| `upstream_repo` | ❌ Optional | Full `owner/repo` if reviewing a fork (e.g. `contributor/myrepo`) |
| `audience` | ❌ Optional | Output audience: `developer` (default) or `owner` |

### Input validation

Before running, the BYOK workflow validates:

- `base_ref` passes `git check-ref-format` (prevents injection via malformed ref)
- `upstream_repo` matches `owner/repo` format if provided (prevents redirect attacks)
- All file reads are contained within the repo root via `is_relative_to()` (prevents path traversal)

!!! warning "Use restricted keys"
    The BYOK workflow uses your repository secrets directly. Use inference-only API keys with no billing or admin access. See [Security → API Key Hardening](security.md#api-key-hardening).

### How to trigger

```
Actions tab → council-byok → Run workflow → fill inputs → Run
```

---

## 📦 Artifacts Reference

| Artifact | File | Workflow | Contents |
|----------|------|----------|----------|
| `council-report` | `council-report.json` | Both | Full `ChairVerdict`: per-reviewer findings, confidence, degraded reasons, final verdict |
| `council-report` | `council-review.md` | BYOK only | Human-readable markdown review (developer or owner format) |

### Finding your artifacts

```
GitHub → Actions tab → Select workflow run → Artifacts section (bottom of summary page)
```

### Getting `council-review.md` from a PR workflow run

The PR workflow currently only uploads `council-report.json`. To get the markdown review:

**Option A** — Run the BYOK workflow against the same branch

**Option B** — Run locally:

```bash
council review --branch main --output-md council-review.md
```

---

## 💻 Local Workflow

Local runs are always advisory by default — they never block a push.

| Mode | Command | Blocks on FAIL? |
|------|---------|----------------|
| Advisory | `council review --branch main` | No |
| Advisory + JSON | `council review --branch main --output-json report.json` | No |
| Advisory + Markdown | `council review --branch main --output-md review.md` | No |
| CI mode | `council review --ci --branch main` | Yes |

CI mode (`--ci`) exits non-zero on `FAIL`. `PASS WITH WARNINGS` always exits zero.

---

## ⏩ Related Pages

- [Getting Started](getting-started.md) — install, init, first review, adding secrets
- [Security](security.md) — BYOK threat model, input validation details, fork PR policy
- [Design](design.md) — the 5-stage pipeline these workflows invoke

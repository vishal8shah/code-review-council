# ❓ FAQ

> Fast answers to the questions that come up most. Jump to a section or scan the whole page.

---

## 🚀 Setup & Install

### Do I need all three API keys?

No. Council works with a single key when all configured models use the same
provider. The generated GitHub workflows are pinned to Gemini, so they require
`GOOGLE_API_KEY`. Local `.council.toml` files only need keys for the providers
they actually reference.

### `council: command not found` — what's wrong?

You're likely outside the virtualenv where you ran `pip install .`. Activate it and retry:

```bash
source .venv/bin/activate
council --version
```

### Does `council init` overwrite my existing `.council.toml`?

No. If `.council.toml` already exists, `init` will not overwrite it. Delete or rename the existing file if you want a fresh scaffold.

### Can I use Council on a private repository?

Yes. The BYOK model means your code goes directly from your CI runner to your LLM provider. Council itself never handles your code. Private repo, public repo — the data flow is identical.

---

## ⚙️ CI & Workflows

### Why does the fork PR review get skipped?

GitHub's security model prevents fork PRs from accessing repository secrets. The `council-review.yml` workflow detects this and skips the LLM step cleanly, uploading a `council-report.json` that explains the skip. This is by design — not a bug. Use `council-byok.yml` (`workflow_dispatch`) to review fork contributor PRs manually.

### How do I review a fork contributor's PR?

1. Go to **Actions → council-byok → Run workflow**
2. Set `base_ref` to your base branch (e.g. `main`)
3. Set `upstream_repo` to the fork (e.g. `contributor/your-repo`)
4. Click **Run workflow**

The BYOK workflow validates both inputs before running.

### Does Council post comments directly to the PR?

Yes — if you run with `--github-pr` and provide a `GITHUB_TOKEN` with write permissions. When this is configured, Council:

- Posts a sticky PR comment with the review summary
- Emits inline workflow annotations for file/line findings
- Posts best-effort inline PR review comments for accepted findings that have file/line evidence

The default `council-review.yml` workflow runs with `--github-pr` only when LLM secrets are available. Fork PRs skip this step.

### The workflow ran but I can’t find the artifact. Where is it?

```
GitHub → Actions tab → Click the workflow run → Scroll to “Artifacts” at the bottom of the summary page
```

Artifacts are retained for 90 days by default (GitHub's setting, not Council's).

### How do I make Council block the merge?

Add `--ci` to your `council review` command in the workflow:

```bash
council review --ci --branch main --output-json council-report.json
```

`--ci` exits non-zero on `FAIL`, which causes the GitHub Actions step to fail and blocks the merge. `PASS WITH WARNINGS` always exits zero.

---

## 💰 Cost & Latency

### How much does a review cost?

It depends on your model selection and diff size. There's no universal number.
A typical focused PR (200-400 lines changed) with mid-tier models may cost a
few cents; preview frontier models such as Gemini 3 Pro Preview can cost more
and take longer. Gate Zero and diff preprocessing are always free.

### How long does a review take?

It depends on model choice, diff size, retries, and reviewer concurrency. With
parallel reviewers enabled, wall-clock time is roughly the slowest single
reviewer plus Chair synthesis. Generated Gemini CI runs sequential reviewers
with larger timeouts to avoid preview-model timeout noise, so it may take a few
minutes on larger diffs.

### How do I reduce cost without losing quality?

| Lever | How to adjust | Trade-off |
|-------|--------------|----------|
| Reviewer models | Use cheaper models for Docs/Architect or a single-provider Gemini preset | Slightly lower reasoning depth or longer preview-model latency |
| Diff size | Review smaller, focused PRs | Requires PR discipline |
| Concurrency | Lower `reviewer_concurrency` for slow/rate-limited providers | More reliable but slower reviews |
| Caching | Enable in `.council.toml` | Same-diff re-runs are free |
| Gate Zero fail-fast | Catches obvious issues before LLM | Already on by default |

---

## 🤖 Models & Config

### How do I change which model a reviewer uses?

Edit `.council.toml`. Each reviewer has a `model` key:

```toml
[council]
chair_model = "gemini/gemini-3-pro-preview"

[[reviewers]]
id = "secops"
name = "Security Operations Reviewer"
model = "gemini/gemini-3-pro-preview"
prompt = "prompts/secops.md"
```

Any model supported by LiteLLM can be used, as long as the matching provider
key is available in your environment or GitHub secrets.

### Can I disable a reviewer I don’t need?

Yes. Set `enabled = false` in `.council.toml` for any reviewer:

```toml
[[reviewers]]
id = "docs"
name = "Documentation Reviewer"
model = "gemini/gemini-3-pro-preview"
prompt = "prompts/docs.md"
enabled = false
```

The Chair will synthesise findings from whichever reviewers remain active.

### Can I add a custom reviewer persona?

Yes — see [Contributing → Adding a Reviewer Persona](contributing.md#adding-a-reviewer-persona) for the full walkthrough.

### What happens if a reviewer times out or returns bad output?

Council enters degraded mode for that reviewer. It:

- Continues with the remaining reviewers
- Reduces the overall confidence score
- Surfaces the failure in `degraded_reasons` in the `ChairVerdict`
- Records `error` and `integrity_error` fields in the JSON artifact

It never silently passes. The degraded state is always visible in CI logs and the JSON report.

### Some models reject JSON mode. Is that still a blocker?

Usually no. Council now tries native JSON mode first and retries with prompt-only JSON fallback when a provider/model rejects `response_format`.

If you're unsure about a model or key setup, run:

```bash
council doctor --branch main
```

The doctor command flags missing provider keys, likely fallback-only models, invalid diff targets, and missing GitHub PR context.

---

## 🛡️ Security

### Do I need to worry about my code being stored by Council?

No. Council is a BYOK orchestration layer. Your code diff goes directly from your CI runner to your LLM provider. Council never sees, stores, or forwards your code or your API keys. See [Security](security.md) for the full data flow.

### My SecOps reviewer flagged something that looks speculative. Is that a bug?

Not necessarily — but it's worth checking the evidence. Every SecOps blocker should include a full exploit chain: untrusted input source → insufficient validation → unsafe sink. If the finding doesn't have all three, the Chair should have downgraded or dismissed it. If you see a speculative blocker making it through to `FAIL`, open an issue — that's a Chair prompt tuning problem.

---

## 📄 Output

### Where is `council-review.md`?

| How you ran Council | Where to find it |
|--------------------|------------------|
| BYOK workflow | Inside the `council-report` artifact (with the JSON) |
| Local CLI | At the path you passed to `--output-md` |
| PR workflow | Not uploaded — run BYOK or local to get it |

### What’s the difference between developer and owner output?

The underlying analysis is identical. The presentation differs:

- **Developer** — file/line references, finding rationale, policy evidence, fix suggestions
- **Owner** — plain-English risk summary, ship/no-ship recommendation, copy-paste fix prompt for an AI coding agent

Set `audience = "owner"` in the BYOK workflow dispatch inputs to get owner output.

### What does `PASS WITH WARNINGS` mean?

The Chair accepted one or more findings as real issues but not severe enough to block the merge. The findings are documented in the report and markdown review. The CI step exits zero — merge is allowed. Engineers should still review the warnings before the next sprint.

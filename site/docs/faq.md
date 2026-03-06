# ❓ FAQ

> Fast answers to the questions that come up most. Jump to a section or scan the whole page.

---

## 🚀 Setup & Install

### Do I need all three API keys?

No. Council works with a single key. You only need keys for the providers your `.council.toml` assigns to reviewer roles. If you're using GPT-4o for all reviewers and Claude for the Chair, you need an OpenAI key and an Anthropic key — no Google key required.

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

It depends on your model selection and diff size. There's no universal number. A typical focused PR (200–400 lines changed) with GPT-4o reviewers and a Claude Chair runs in the range of a few cents. Large multi-file refactors with heavier models will cost more. Gate Zero and diff preprocessing are always free.

### How long does a review take?

Typically 30–60 seconds for a focused PR with parallel reviewers enabled. The four specialist reviewers run concurrently, so wall-clock time is roughly the slowest single reviewer, not the sum of all four.

### How do I reduce cost without losing quality?

| Lever | How to adjust | Trade-off |
|-------|--------------|----------|
| Reviewer models | Use `gpt-4o-mini` for Docs/Architect | Slightly lower reasoning depth |
| Diff size | Review smaller, focused PRs | Requires PR discipline |
| Concurrency | Already parallel by default | No change needed |
| Caching | Enable in `.council.toml` | Same-diff re-runs are free |
| Gate Zero fail-fast | Catches obvious issues before LLM | Already on by default |

---

## 🤖 Models & Config

### How do I change which model a reviewer uses?

Edit `.council.toml`. Each reviewer has a `model` key:

```toml
[reviewers.secops]
model = "gpt-4o"

[reviewers.qa]
model = "gpt-4o"

[chair]
model = "claude-3-5-sonnet-20241022"
```

Any model supported by the configured provider SDK can be used.

### Can I disable a reviewer I don’t need?

Yes. Set `enabled = false` in `.council.toml` for any reviewer:

```toml
[reviewers.docs]
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

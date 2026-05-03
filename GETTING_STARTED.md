# Getting Started

## What this tool does

**Code Review Council** reviews code changes in a Git repository and helps catch:

- security issues
- quality risks
- maintainability problems
- common pitfalls in AI-generated code

It supports two presentation styles:

- **Developer audience** — technical findings, evidence, file/line references, fix guidance, and reviewer detail
- **Owner audience** — plain-English summaries, business impact, fix prompts, and shareable reports for product owners, founders, or stakeholders

This is especially useful when code is written or heavily assisted by AI tools like Cursor, Copilot, Lovable, Claude, and similar workflows.

---

## What this tool is not

This tool is **not**:

- a full application security audit platform
- a hosted SaaS product
- a replacement for engineering judgment
- a guarantee that code is production-safe

It reviews the **current code diff / change set**, not your entire product or infrastructure by default.

---

## Prerequisites

Before you start, make sure you have:

- **Python 3.12 or newer** ← required; install will fail on older versions
- **Git**
- a local Git repository to review
- an API key for a supported LLM provider; generated GitHub workflows currently use Google/Gemini
- basic terminal familiarity

---

## Install

Clone the repo and install it in a virtual environment:

```bash
git clone <YOUR_REPO_URL>
cd code-review-council

python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -U pip
pip install .
```

If your system uses a different Python launcher, adjust `python3.12` accordingly.

---

## Set your API key

Export an API key for the model provider you plan to use. The generated GitHub
Actions workflows are pinned to Gemini, so `GOOGLE_API_KEY` is the key required
for the default CI path.

```bash
# Google / Gemini (required for generated GitHub workflows)
export GOOGLE_API_KEY=your_key_here

# OpenAI
export OPENAI_API_KEY=your_key_here

# Anthropic
export ANTHROPIC_API_KEY=your_key_here
```

If your local `.council.toml` uses a different LiteLLM-supported provider, set
that provider's key instead or in addition.

---

## Run a preflight check

Before your first review, validate the repo, branch target, configured models, and
available keys:

```bash
council doctor --branch main
```

`council doctor` warns when a configured model is likely to need prompt-only JSON
fallback and fails fast on blocking setup issues such as missing keys, invalid branch
targets, or missing GitHub PR context. It also prints the active review profile
and the next command to run so you can confirm model, timeout, audience, and
integrity settings before making a paid review call.

---

## Initialize in your target repo

Run `council init` from the root of the repository you want to review:

```bash
cd /path/to/your-project
council init
```

This creates:

- `.council.toml` — configuration for models, reviewers, and enforcement
- `.councilignore` — files to exclude from review (lock files, generated code, etc.)
- `prompts/*.md` — default persona prompts referenced by `.council.toml`
- `.github/workflows/council-review.yml` — GitHub Actions CI workflow
- `.github/workflows/council-byok.yml` — manual BYOK workflow for fork contributors

Open `.council.toml` to adjust models, reviewers, and settings before running your first review.

---

## Run your first review

**Review staged changes:**
```bash
council review --staged
```

**Review changes against your main branch:**
```bash
council review --branch main
```

**CI mode (exits non-zero on FAIL):**
```bash
council review --ci --branch main
```

**CI mode with GitHub PR sticky summary + inline comments + annotations:**
```bash
council review --ci --github-pr --branch main
```
Optional env tuning for flaky/rate-limited runners:
- `COUNCIL_GITHUB_MAX_RETRIES` (default: `2`)
- `COUNCIL_GITHUB_RETRY_BACKOFF_SECONDS` (default: `1.0`)
- `COUNCIL_GITHUB_HTTP_TIMEOUT` (default: `10`)
- If you hit model TPM/rate-limit errors, lower `[council].reviewer_concurrency` in `.council.toml`. Generated Gemini CI uses `1` for reliability.
- On fork PRs where repo secrets are unavailable, the default workflow now skips LLM review and writes a placeholder `council-report.json` artifact instead of failing.

---

## Required gates for your TS/JS repos

Use `.github/workflows/council-openai-gate.yml` when you want Council to be a
required PR check in another repo. Unlike `council-review.yml`, it installs
Council from GitHub instead of assuming the target repo contains Council source.
It requires `OPENAI_API_KEY`, fails closed if the key is missing, and writes a
temporary CI config with:

```toml
[council]
chair_model = "openai/gpt-5.5"
chair_reasoning_effort = "medium"
timeout_seconds = 360
reviewer_timeout_seconds = 240
reviewer_concurrency = 2
```

Before making it a protected-branch requirement, pin `COUNCIL_INSTALL_SPEC` in
the workflow to a release tag or commit SHA and run it on a few representative
PRs to tune `.councilignore` and any repo-specific analyzer opt-outs.

---

## Fork PRs: Run full Council with your own API key (BYOK)

When contributing from a fork, upstream repository secrets are often unavailable. Use the fork-safe BYOK workflow in your fork instead:

1. In your fork repository, add `GOOGLE_API_KEY` as an Actions secret.
2. Open **Actions** in your fork and run workflow **Code Review Council (BYOK - Fork)**.
3. Run the workflow from your PR branch (select the branch in the dispatch UI).
4. Set `base_ref` (usually `main`), optional `audience` (`developer` or `owner`), and optional `upstream_repo` (`owner/repo`) if you want diffs against upstream instead of your fork's base branch.
5. Download the `council-report` artifact (`council-report.json` + `council-review.md`).
   - `council-review.md` is the markdown review output from the BYOK run.
6. Paste the review results into the upstream PR discussion.

Security note: only run BYOK workflows on branches you control. Never run BYOK on branches from unknown contributors. Use restricted/low-quota API keys.

---

## Local BYOK run

You can also run the full CI-style review locally with your own environment keys:

```bash
export GOOGLE_API_KEY=your_key_here
# Optional only if your local .council.toml references them:
export OPENAI_API_KEY=your_key_here
export ANTHROPIC_API_KEY=your_key_here

council review --ci --branch main --audience developer --output-json council-report.json --output-md council-review.md
```

This produces local JSON + Markdown outputs without posting to GitHub PR comments.
The markdown file is written to the path passed with `--output-md` (for example
`council-review.md`) and includes deterministic next steps, fix prompts, and
verification guidance for accepted findings.

**Generate an owner-friendly HTML report:**
```bash
council review --audience owner --output-html owner-report.html
```
Open the generated file in your browser.

**Generate an owner-friendly Markdown report:**
```bash
council review --audience owner --output-md owner-review.md
```
Useful for Slack, email, PR comments, or docs.

---

## Review history and debt signals

Phase 4B adds local review history so you can see trends across runs without
committing artifacts to the repo. By default Council stores history in the OS
user cache and does not store raw diffs, evidence snippets, suggestions, fix
prompts, Chair reasoning text, or model-generated finding descriptions.

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

`[DEBT]` means the same privacy-preserving finding fingerprint appeared in
three consecutive review runs for this repo. Findings seen in two or more runs
are shown as repeat candidates, but are not labeled debt yet.

```toml
[history]
enabled = true
path = ""
retention_days = 180
store_finding_text = false
```

Keep `path = ""` unless you need a repo-local database. Configured paths must
be relative to the repo and must not traverse outside it; absolute paths and
`~` escapes are rejected for safety.

If the history database cannot be opened, has a newer unsupported schema, or is
corrupt, `council history summary` exits with a concise error instead of a
Python traceback. This only affects the explicit inspection command; review
runs still treat history writes as best-effort and do not change verdicts.

## Bounded repo test context

Phase 4C lets Council scan existing repo test files for changed source files so
QA reviewers do not mistake "tests outside the diff" for "no tests found." The
scan is bounded, respects `.councilignore`, skips heavy directories such as
`.git`, `node_modules`, build/cache folders, and virtual environments, and does
not prove test quality or complete coverage.

```toml
[context]
full_repo_tests = true
max_test_files = 500
max_test_file_bytes = 20000
```

If the scan hits a cap or cannot read a test file, Council keeps the review
non-blocking and marks the repo-wide test context as incomplete.

## Language analyzers

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

## Recommended first workflow

For the fastest first success:

1. Make a small code change in your repo
2. Stage the change:
   ```bash
   git add .
   ```
3. Run a developer review:
   ```bash
   council review --staged
   ```
4. Generate an owner-friendly report:
   ```bash
   council review --staged --audience owner --output-html owner-report.html
   ```
5. Open `owner-report.html` in your browser
6. Use the copy/paste fix prompt on any issue card with your AI coding tool
7. Re-run the review after the fix to confirm it passes

---

## Sharing results with a PM, founder, or stakeholder

**Owner HTML** — best for browser viewing, async stakeholder review, polished summaries:
```bash
council review --audience owner --output-html owner-report.html
```

**Owner Markdown** — best for Slack, email, GitHub PR comments, quick copy/paste:
```bash
council review --audience owner --output-md owner-review.md
```

These owner outputs use the same underlying analysis as developer mode. Only the presentation changes — the same findings, translated into plain English.

---

## Model presets (quick guidance)

If you want local parity with the generated GitHub workflows, use
`gemini/gemini-3-pro-preview` for the Chair and all reviewers, set
`reviewer_concurrency = 1`, and give both `timeout_seconds` and
`reviewer_timeout_seconds` enough room for slower preview-model calls.

If you want the local scaffold defaults, use chair `openai/gpt-4o` with reviewer mix:
- secops/qa: `openai/gpt-5.2`
- architect: `openai/gpt-4o`
- docs: `openai/gpt-4o-mini`

If you want a stronger synthesis model, keep the same reviewer mix and use
`anthropic/claude-sonnet-4-6` as `chair_model`.

---

## Troubleshooting

**Python version error during install**
Check your Python version:
```bash
python --version
```
This repo requires Python 3.12+. Use `python3.12` or install a compatible version.

**No review output / empty diff**
Make sure you either:
- staged changes with `git add .` before using `--staged`, or
- specified the correct branch with `--branch main`

**Missing API key**
If the review fails immediately, confirm your provider API key is set in your environment:
```bash
echo $OPENAI_API_KEY
echo $ANTHROPIC_API_KEY
echo $GOOGLE_API_KEY
```
Then run:
```bash
council doctor --branch main
```
It will tell you which configured models are missing provider keys and whether your
current setup is blocking or just likely to use JSON fallback transport.


**Prompt-injection findings in test fixtures**
If CI flags prompt-injection on test fixture strings, ensure the changed file is under `tests/` or `__tests__/`, matches `*.spec.ts(x)` / `*.test.ts(x)` / `*.spec.js(x)` / `*.test.js(x)`, or is named `conftest.py`, so Gate Zero test-file exclusions apply.
For real source files, treat this as a genuine security warning and sanitize untrusted prompt content.
Secret scanning still runs for test files; committed tokens in tests will still block CI.

**Owner report mentions a "fallback" or "deterministic"**
This is a safety feature, not a failure. It means:
- the technical findings still exist and are shown in the technical appendix
- the plain-English translation or one of the model calls used a fallback transport path
  instead of native `response_format`

The findings are not hidden.

**CI review found no useful diff**
Confirm that your CI workflow compares against the correct base branch and that the workflow runs on code-changing events.

---

## What to expect from the outputs

**Developer audience** — best for engineers who want:
- file/line references
- code evidence
- reviewer rationale
- accepted blockers and warnings by category
- copy/paste fix prompts, verification steps, and review next steps
- per-reviewer `error` and `integrity_error` fields in JSON output for CI triage, including sanitized schema field/type diagnostics for malformed findings

**Owner audience** — best for product owners, founders, or semi-technical stakeholders who want:
- merge recommendation (SAFE TO MERGE / MERGE WITH CAUTION / FIX BEFORE MERGE)
- risk level
- plain-English explanation of each issue
- a fix prompt to paste into their AI coding tool
- what to test after the fix
- whether a developer needs to review the fix

---

## Next steps

Once your first review works:

1. Tune `.council.toml` — choose models, adjust reviewers, set enforcement mode
2. Enable the GitHub Actions workflow for automatic PR reviews
3. Share owner report artifacts with stakeholders when useful
4. Use `council history summary` to spot repeated review patterns before adding heavier automation

---

## Honest expectation setting

This tool is useful today, but it works best when operated by someone comfortable with Git, Python, API keys, and terminal workflows.

The owner audience output is designed to make results much easier to understand and share — even if the person installing and running the tool is still more technical than the intended reader.

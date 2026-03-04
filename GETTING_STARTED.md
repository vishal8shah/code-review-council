# Getting Started

## What this tool does

**Code Review Council** reviews code changes in a Git repository and helps catch:

- security issues
- quality risks
- maintainability problems
- common pitfalls in AI-generated code

It supports two presentation styles:

- **Developer audience** — technical findings, evidence, file/line references, and reviewer detail
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
- an API key for a supported LLM provider (OpenAI or Anthropic)
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

Export an API key for the model provider you plan to use:

```bash
# OpenAI
export OPENAI_API_KEY=your_key_here

# Anthropic
export ANTHROPIC_API_KEY=your_key_here
```

If you use a different provider supported by LiteLLM, set that provider's key instead.

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
- `.github/workflows/council-review.yml` — GitHub Actions CI workflow

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
```


**Prompt-injection findings in test fixtures**
If CI flags prompt-injection on test fixture strings, ensure the changed file is under `tests/` (or `conftest.py`) so Gate Zero test-file exclusions apply.
For real source files, treat this as a genuine security warning and sanitize untrusted prompt content.
Secret scanning still runs for test files; committed tokens in tests will still block CI.

**Owner report mentions a "fallback" or "deterministic"**
This is a safety feature, not a failure. It means:
- the technical findings still exist and are shown in the technical appendix
- the plain-English translation used a deterministic fallback instead of the LLM translation path

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
- per-reviewer `error` and `integrity_error` fields in JSON output for CI triage

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

---

## Honest expectation setting

This tool is useful today, but it works best when operated by someone comfortable with Git, Python, API keys, and terminal workflows.

The owner audience output is designed to make results much easier to understand and share — even if the person installing and running the tool is still more technical than the intended reader.

# 10 Minute Quickstart

Use this path when a team wants to see Council's value quickly: install the
CLI, run one local review, generate a stakeholder report, and add the GitHub PR
gate. It is intentionally shorter than the full [Getting Started](getting-started.md)
guide.

## What You Will Prove

By the end, you should have:

- `council --version` working in your shell.
- A `.council.toml` and generated GitHub workflow in the repo you want to
  review.
- A local advisory review command you can rerun after an AI coding agent changes
  code.
- A JSON report for automation and an owner-friendly HTML report for
  stakeholders.
- A GitHub Actions PR gate ready for a pilot branch.

!!! warning "Bring your own model key"
    Council uses your model-provider keys. Use restricted inference-only keys,
    store CI keys as GitHub Actions secrets, and never commit secrets in
    `.council.toml`, prompts, reports, or issue text.

## Minute 0-2: Install And Verify

From this repository while Council is pre-PyPI:

```bash
git clone https://github.com/vishal8shah/code-review-council
cd code-review-council
pip install .
council --version
```

Expected shape:

```text
Code Review Council <version>
```

## Minute 2-4: Initialize The Target Repo

Move into the repository you want Council to review:

```bash
cd ../your-project
council init
```

This creates `.council.toml`, `.councilignore`, reviewer prompts, and GitHub
workflow scaffolding. Read the generated next steps before running a paid model
review.

## Minute 4-5: Add A Key And Run Doctor

The default generated GitHub workflows use Gemini, so start with
`GOOGLE_API_KEY` unless you changed `.council.toml`.

```bash
export GOOGLE_API_KEY=...
council doctor --branch main
```

`doctor` prints the active review profile, model routing, timeout/concurrency
settings, and the next command to run. Fix any `FAIL` checks before continuing.

## Minute 5-7: Run A Local Advisory Review

Run a local review against your main branch:

```bash
council review --branch main \
  --output-json council-report.json \
  --output-md council-review.md
```

Local review is advisory. It does not block your push. Use it after Codex,
Claude Code, OpenClaw, Cursor, or another coding agent changes a diff.

Check these fields first:

- Final verdict: `PASS`, `PASS WITH WARNINGS`, or `FAIL`.
- `degraded` and `degraded_reasons`.
- Accepted blockers and warnings with file or policy evidence.
- Reviewer errors, integrity errors, and transport notes.

Do not treat a degraded run as a fully trusted clean bill of health.

## Minute 7-8: Generate A Stakeholder Report

Owner mode is a presentation layer over the same accepted findings. It must not
hide or soften technical blockers.

```bash
council review --branch main \
  --audience owner \
  --output-html owner-report.html
```

Share `owner-report.html` when a product owner, founder, or engineering manager
needs a plain-English summary plus a technical appendix.

## Minute 8-10: Pilot The GitHub PR Gate

Commit the generated workflow files on a non-protected branch first:

```bash
git add .council.toml .councilignore prompts .github/workflows
git commit -m "ci: add Council review gate"
git push
```

Then:

1. Add `GOOGLE_API_KEY` as a repository Actions secret for the default workflow.
2. Open one pilot PR from your own branch.
3. Inspect the PR comment and `council-report.json` artifact.
4. Confirm `FAIL` blocks only in CI mode and `PASS WITH WARNINGS` exits zero.
5. Make Council a required status check only after the pilot is stable.

For external repositories that should use an OpenAI-backed required gate without
vendoring Council source, generate only that workflow:

```bash
council init --workflow-profile openai-gate
```

Keep its `COUNCIL_INSTALL_SPEC` pinned to a release tag or commit SHA. Do not
use a moving branch such as `main` for protected branch rollout.

## Good First Outcome

A successful first session does not need a perfect review. It needs visible,
auditable behavior:

- Clean PRs produce `PASS` or an expected `PASS WITH WARNINGS`.
- Risky PRs produce findings with evidence.
- Invalid model output, reviewer timeouts, and dropped findings are visible.
- JSON, Markdown, HTML, terminal, and PR output describe the same verdict.
- The team knows which accepted findings a coding agent should fix next.

## Where To Go Next

- [Getting Started](getting-started.md) for the full setup reference.
- [Adoption Guide](adoption-guide.md) for multi-repo rollout.
- [Agent Loop](agent-loop.md) for Codex, Claude Code, OpenClaw, and similar
  repair loops.
- [Security](security.md) for BYOK and untrusted input rules.
- [Commercial Readiness](https://github.com/vishal8shah/code-review-council/blob/main/COMMERCIAL_READINESS.md)
  for the product roadmap.

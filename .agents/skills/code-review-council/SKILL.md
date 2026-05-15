---
name: code-review-council
description: Use when reviewing or changing Code Review Council reviewer logic, Chair synthesis, reporters, integrity policy, prompts, GitHub PR reporting, analyzers, output audiences, CI gate behavior, config schema, or model transport.
---

# Code Review Council Skill

Use this skill when working inside the Code Review Council repository or a fork
of it.

## Triggers

Apply this workflow when asked to:

- Review a diff.
- Modify reviewer logic.
- Modify Chair synthesis.
- Modify reporter output.
- Modify integrity policy.
- Modify prompts.
- Modify GitHub PR reporting.
- Add a language analyzer.
- Add an output audience.
- Change CI gate behavior.
- Change config schema or model transport.

## Required Context To Inspect

Always inspect:

- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/INTEGRITY_POLICY.md`
- The files directly touched by the request.
- The nearest existing tests in `tests/`.

For reviewer, prompt, or Chair work, also inspect:

- `council/reviewers/base.py`
- `council/chair.py`
- `council/orchestrator.py`
- `council/schemas.py`
- Relevant `prompts/*.md`

For reporter work, also inspect:

- `council/reporters/`
- `tests/test_github_reporter.py`
- `tests/test_terminal_reporter.py`
- Any tests covering markdown, JSON, or owner output in `tests/test_council.py`

For GitHub workflow work, also inspect:

- `.github/workflows/`
- `council/reporters/github_pr.py`
- `site/docs/workflows.md`

For analyzer work, also inspect:

- `council/analyzers/`
- `council/gate_zero.py`
- `council/review_pack.py`
- Tests covering analyzer and test-path behavior.

## Review Process

1. Confirm the repository boundary and current branch.
2. Read the relevant code, docs, config, prompts, and tests before editing.
3. Use `.agent/PLANS.md` for risky or multi-file work.
4. Keep the patch narrow.
5. Add or update tests for behavior changes.
6. Check reporter parity for output changes.
7. Check docs for CLI or public behavior changes.
8. Run focused validation, then the broader validation needed for the change.

## Block Conditions

Do not ship changes that introduce or hide:

- Silent PASS after reviewer, Chair, transport, parsing, or integrity failure.
- Invalid JSON being treated as success.
- Dropped findings not being surfaced.
- Evidence-free blockers.
- Security findings without a realistic exploit path.
- Chair synthesis hiding serious dissent.
- Reporter drift across JSON, markdown, HTML, terminal, GitHub PR, or owner
  output.
- Docs that disagree with current CLI behavior.
- New dependencies for documentation-only changes.

## Output Format

For implementation work, respond with:

```text
Summary: concise description of what changed.
Validation: exact commands run and result.
Docs/reporting impact: affected public surfaces.
Residual risk: anything not tested or intentionally deferred.
```

For code review work, lead with findings ordered by severity and include tight
file/line references.

## Validation Checklist

- `pytest -q` or `py -3.13 -m pytest -q`
- `ruff check .` or `py -3.13 -m ruff check .`
- `mkdocs build -f site/mkdocs.yml` or local equivalent when docs changed
- Focused tests for changed behavior
- Reporter parity checked when reporters or verdict fields change
- Integrity cases checked when reviewer, Chair, transport, or schema behavior
  changes

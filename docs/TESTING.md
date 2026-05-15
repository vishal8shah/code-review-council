# Testing Guide

Use this guide when changing Code Review Council. Validation is mandatory before
an agent says work is complete.

## Install

Project command:

```bash
pip install -e .
```

Windows local command form:

```powershell
py -3.13 -m pip install -e .
```

The project requires Python 3.12 or newer. The GitHub workflows use Python 3.12;
this Windows checkout has been validated with `py -3.13`.

## Full Test Suite

Project command:

```bash
pytest -q
```

Windows local command form:

```powershell
py -3.13 -m pytest -q
```

The current suite is a flat `tests/` directory. Do not assume `tests/unit/` or
`tests/integration/` exists.

## Lint

Project command:

```bash
ruff check .
```

Windows local command form:

```powershell
py -3.13 -m ruff check .
```

Gate Zero's default Python linter command is `ruff check --diff`, but repository
validation should use `ruff check .`.

## Docs Build

Project command:

```bash
mkdocs build -f site/mkdocs.yml
```

Windows local command form:

```powershell
py -3.13 -m mkdocs build -f site/mkdocs.yml
```

Optional stricter check:

```powershell
py -3.13 -m mkdocs build -f site/mkdocs.yml --strict
```

## Narrow Test Selection

Use focused tests while developing, then run the full suite before completion.

```bash
pytest tests/test_chair_synthesize.py -q
pytest tests/test_github_reporter.py -q
pytest tests/test_history.py tests/test_history_cli.py -q
pytest tests/test_llm_transport.py -q
pytest tests/test_review_pack_support_context.py tests/test_support_context_prompts.py -q
pytest tests/test_terminal_reporter.py -q
```

## Reporter Regression Testing

Reporter changes must verify every affected surface:

- Terminal output preserves verdict, accepted blockers, warnings, degraded state,
  and next steps.
- Markdown output works for developer and owner audiences.
- JSON output includes `degraded`, `degraded_reasons`, reviewer `error`,
  reviewer `integrity_error`, output modes, and transport notes.
- HTML output preserves the same accepted findings as markdown.
- GitHub PR output sanitizes untrusted text and surfaces degraded integrity
  signals.

Use existing reporter tests as the first place to add coverage.

## CLI Behavior Testing

CLI changes should cover:

- `council review` advisory behavior.
- `council review --ci` exit behavior.
- `--branch`, `--staged`, and empty-diff behavior.
- `--audience developer` and `--audience owner`.
- `--output-json`, `--output-md`, `--output-html`.
- `--github-pr` behavior when env vars or PR context are missing.
- `council doctor` setup diagnostics.
- `council history summary` error handling and output.

## GitHub Reporter Testing

GitHub reporter changes should cover:

- Missing token, repository, event path, or PR number.
- Safe GitHub event-file reading.
- Annotation sanitization.
- Sticky comment body content.
- Inline comment deduplication.
- API URL validation.
- Retry behavior and API failures.

GitHub API failures must not alter the review verdict.

## Prompt And Schema Compatibility

Prompt, reviewer, transport, Chair, and schema changes should cover:

- Valid reviewer JSON.
- Invalid reviewer JSON.
- Malformed findings and dropped finding diagnostics.
- Reviewer exceptions or timeouts.
- Chair invalid JSON or transport failure.
- Owner-presentation fallback preserving all accepted findings.
- New or changed fields in `council/schemas.py`.

## Manual Verification Format

When manual verification is useful, record it in the PR description:

```text
Command: <exact command>
Result: <pass/fail and key output>
Artifacts inspected: <report paths or CI output>
Behavior checked: <what the artifact proves>
Residual risk: <anything not covered>
```

Manual verification is not a substitute for tests when behavior changes.

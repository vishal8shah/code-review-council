# Getting Started with Code Review Council

## Prerequisites

- **Python 3.12+** is required.
- At least one LLM API key: `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY`.

## Quick Install

```bash
pip install .
```

## Initialize Your Repository

```bash
cd your-repo
council init
```

This creates:
- `.council.toml` — main configuration
- `.councilignore` — files to exclude from review
- `prompts/` — default reviewer prompt files (secops, qa, architecture, docs)
- `.github/workflows/council-review.yml` — GitHub Actions workflow

## Run a Local Review

```bash
# Review uncommitted changes (advisory mode)
council review

# Review staged changes only
council review --staged

# Diff against a branch
council review --branch main
```

## Audience Modes

### Developer (default)
Full technical detail with all findings, reviewer panel, and chair rationale:

```bash
council review --branch main
```

### Owner
Executive summary with trust signal, top risks, and reviewer health:

```bash
council review --branch main --audience owner
council review --branch main --audience owner --output-html report.html
council review --branch main --audience owner --output-md owner-review.md
```

## Output Formats

| Flag | Description |
|------|-------------|
| `--output-md PATH` | Markdown report (audience-aware) |
| `--output-html PATH` | Self-contained HTML report (owner-friendly) |
| `--output-json PATH` | Machine-readable JSON report |
| `--github-pr` | Post results as a GitHub PR comment + annotations |

## CI Mode

```bash
council review --ci --branch main --github-pr --output-json report.json
```

In CI mode:
- Exit code 1 on FAIL verdict
- JSON report is auto-generated
- `--github-pr` posts a sticky comment to the PR and emits workflow annotations
- Integrity policy (`on_integrity_issue = "fail"`) blocks degraded runs

## Configuration

Edit `.council.toml` to customize:
- **Chair model** — `chair_model = "openai/gpt-4o"`
- **Reviewers** — add/remove/customize reviewer personas
- **Enforcement** — `ci_block_on`, `on_integrity_issue`
- **Gate Zero** — static checks (secrets, docstrings, type hints, linters)
- **Preprocessor** — token budgets, file priorities

## Custom Reviewers

Add a custom reviewer with `class_path`:

```toml
[[reviewers]]
id = "compliance"
name = "Compliance Reviewer"
model = "anthropic/claude-sonnet-4-20250514"
prompt = "prompts/compliance.md"
class_path = "mypackage.reviewers:ComplianceReviewer"
enabled = true
```

The class must extend `council.reviewers.base.BaseReviewer`.

# Getting Started

This page is an adapted, web-friendly version of the repository `GETTING_STARTED.md` setup flow.

## 1) Install

```bash
pip install .
```

## 2) Initialize

Run inside the repository you want to review:

```bash
council init
```

This creates `.council.toml` and workflow scaffolding.

## 3) Set API keys (BYOK)

Use one or more provider keys:

```bash
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
export GOOGLE_API_KEY=...
```

Bring-your-own-key means your workflow/account controls provider access and spend.

## 4) Run locally

```bash
# Review current working tree against default branch logic
council review

# Explicit branch target
council review --branch main

# CI-style behavior (non-zero on fail)
council review --ci --branch main --output-json council-report.json
```

## 5) Where artifacts appear

- `--output-json <path>` writes JSON findings to your chosen path.
- `--output-md <path>` writes markdown output to your chosen path.
- In GitHub Actions BYOK workflow, `council-report.json` and `council-review.md` are uploaded in the artifact.

## BYOK note

Use restricted keys and run reviews only on trusted branches/repositories you control.

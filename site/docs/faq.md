# FAQ

## Why does fork PR skip?

Fork PRs often do not have access to repository secrets. In that case, the PR workflow skips the full LLM review and still uploads `council-report.json` explaining the skip.

## Where are outputs?

- PR workflow artifact: `council-report.json`
- BYOK workflow artifact: `council-report.json` and `council-review.md`
- Local runs: wherever you point `--output-json` / `--output-md`

## How do I change reviewer models?

Update reviewer model settings in `.council.toml` under the reviewer entries and chair model settings.

## How do I tune cost/latency?

Use fewer or smaller models, reduce reviewer concurrency, and review smaller diffs. Results vary by provider, model, and diff size.

## Does this post comments to PR?

- If you run with `--github-pr` and provide a `GITHUB_TOKEN` with permissions, Council posts a sticky PR comment and emits workflow annotations.
- The default PR workflow in this repo runs with `--github-pr` only when LLM secrets are available; fork PRs usually skip.

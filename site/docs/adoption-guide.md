# Multi-Repo Adoption Guide

Use this guide when you want Code Review Council to run as a required GitHub
PR gate in a repository that does not vendor the Council source.

## Recommended Path

1. Add `OPENAI_API_KEY` as a repository Actions secret.
2. Generate only the reusable OpenAI gate workflow:

   ```bash
   council init --workflow-profile openai-gate
   ```

3. Confirm `.github/workflows/council-openai-gate.yml` pins Council to a release
   tag or commit SHA:

   ```yaml
   env:
     COUNCIL_INSTALL_SPEC: git+https://github.com/vishal8shah/code-review-council.git@v0.2.0
   ```

4. Tune `.councilignore` so lockfiles, generated files, vendored dependencies,
   and build outputs do not consume review budget.
5. Run the workflow on a non-protected branch before enabling branch protection.
6. Once the pilot is healthy, mark the Council workflow as a required status
   check in branch protection.

## What The OpenAI Gate Does

The generated `council-openai-gate.yml` workflow:

- Runs on `pull_request`.
- Installs Council from `COUNCIL_INSTALL_SPEC`.
- Fails closed when `OPENAI_API_KEY` is unavailable.
- Uses `openai/gpt-5.5` with `chair_reasoning_effort = "medium"` for Chair
  synthesis.
- Uses `openai/gpt-5.2` reviewers.
- Enables Python, TypeScript, and JavaScript Gate Zero analyzers.
- Runs `council review --ci --github-pr --branch "$BASE_REF"` with
  `BASE_REF` supplied through the workflow environment.
- Uploads `council-report.json` as an artifact.

## Pilot Definition Of Done

Before making Council required across multiple repositories, complete one pilot
repo and confirm:

- A clean PR produces a non-degraded `PASS` or expected `PASS_WITH_WARNINGS`.
- An intentionally risky PR produces a useful blocking result or clear warning.
- There are no missing-secret, install, model-routing, or base-ref failures.
- The PR comment and JSON artifact are understandable to the repo maintainers.

## Language Capability Matrix

| Capability | Python | TypeScript | JavaScript | Go / Rust / Java / Ruby / other |
|---|---|---|---|---|
| Diff ingestion and LLM review | Yes | Yes | Yes | Yes |
| Gate Zero deterministic analyzer | AST-based | Parser-free heuristics | Parser-free heuristics | Not yet |
| ReviewPack symbol extraction | AST-based | Parser-free export heuristics | Parser-free export heuristics | Limited diff heuristics |
| Repo-wide test context | Python import and filename matching | Relative import and filename matching | Relative import and filename matching | Filename/context only |

Council does not replace ESLint, `tsc`, compilers, type-aware static analyzers,
or language-native test suites. Keep those tools in your CI. Council adds an
evidence-based review layer over the PR diff and structured context.

## Release Checklist

After the release PR merges:

1. Create and push the release tag:

   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

2. Verify installation from the tag:

   ```bash
   pip install git+https://github.com/vishal8shah/code-review-council.git@v0.2.0
   ```

3. Run a manual OpenAI smoke validation before broad rollout:

   - GPT-5.5 Chair with `chair_reasoning_effort = "medium"`.
   - GPT-5.2 reviewer routing.
   - No unsupported non-default `temperature` on GPT-5-family reasoning calls.

4. Pilot in one real TypeScript or JavaScript repo before enabling required
   branch protection broadly.

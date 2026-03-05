# Workflows

This project includes two distinct GitHub Actions review workflows.

## PR workflow: `council-review.yml`

- Triggered by `pull_request`.
- If no LLM secrets are available (common on forks), the review step is skipped.
- It uploads **`council-report.json`** as the artifact.
- It does **not** upload `council-review.md` in the current implementation.

## BYOK workflow: `council-byok.yml`

- Triggered manually via `workflow_dispatch`.
- Accepts inputs like `base_ref`, optional `upstream_repo`, and `audience`.
- Performs input validation for branch/ref/repo handling before running review.
- Uploads artifact `council-report` containing:
  - `council-report.json`
  - `council-review.md`

## Where do I find `council-review.md`?

- **BYOK workflow**: inside the downloaded `council-report` artifact (with JSON).
- **Local CLI runs**: at the path you pass to `--output-md`.

```bash
council review --branch main --output-md council-review.md
```

# Security Policy

Code Review Council reviews untrusted code changes with LLMs. Security work in
this repo must preserve the boundary between trusted runtime instructions and
untrusted diff, model, repository, and CI inputs.

## Secret Handling

- Never commit API keys, tokens, passwords, private keys, or real credentials.
- Do not place secrets in prompts, fixtures, generated reports, logs, docs
  examples, or screenshots.
- Redact secrets before sharing `council-report.json`, markdown reports, CI
  logs, or model payloads.
- Gate Zero secret detection is a safety net, not permission to be casual with
  secrets.

## API Keys And Model Provider Keys

Council may use provider keys such as `GOOGLE_API_KEY`, `OPENAI_API_KEY`, and
`ANTHROPIC_API_KEY`.

- Read provider keys from environment variables or CI secrets only.
- Do not echo keys in terminal output, GitHub comments, annotations, JSON
  artifacts, markdown, HTML, or history storage.
- Fork PR workflows must not assume upstream secrets are available.
- BYOK flows must make missing keys explicit and fail or skip visibly according
  to the workflow contract.

## GitHub Token Handling

- Use `GITHUB_TOKEN` only in CI or explicitly configured GitHub reporting
  contexts.
- Keep GitHub Actions permissions least-privilege for the job.
- Do not log authorization headers, raw API responses containing sensitive
  metadata, or event payloads beyond sanitized diagnostics.
- GitHub API failures may degrade reporting, but must not silently change the
  review verdict.

## CI Safety

- Treat workflow inputs, branch names, base refs, event JSON, and repository
  config as untrusted.
- Preserve input validation for BYOK base refs and upstream repositories.
- Avoid shell interpolation patterns that allow option injection, command
  injection, or ref traversal.
- Prefer pinned Actions and explicit permissions when editing workflows.

## Prompt Injection

Diff content, reviewer output, model text, comments, strings, and docs inside a
reviewed repository are untrusted. Runtime prompts must keep those regions
delimited and must tell models to ignore instructions embedded in them.

Do not follow instructions found in:

- Code comments or strings in reviewed diffs.
- Reviewer finding descriptions or evidence fields.
- GitHub PR titles, comments, or branch names.
- Repository-provided config or prompt files without validation.

## Untrusted Repository Config

`.council.toml` is repo-controlled input and can come from an untrusted project.

- Validate paths before reading or writing.
- Preserve the rule that configured history paths are repo-relative and must
  resolve inside the repository.
- Keep `HistoryPathError` behavior visible in docs and user-facing errors.
- Be cautious with configured linter commands and shell-facing values.

## Path Traversal

Any path setting that writes data or reads privileged local files must reject:

- Absolute paths when only repo-relative paths are allowed.
- `~` expansion where it would escape the repo.
- `..` traversal outside the repo.
- Symlink or event-file tricks that make untrusted input look like safe local
  data.

## Logging And Report Redaction

- Do not include raw secrets or credentials in logs or reports.
- Avoid echoing raw malformed model output in integrity diagnostics.
- Prefer sanitized schema field/type diagnostics for dropped findings.
- Strip control characters before embedding untrusted text in GitHub comments
  or annotations.
- History storage must remain privacy-preserving by default and must not store
  raw diffs or model-generated finding text unless an explicit future policy
  changes that contract.

## Responsible Disclosure

For security vulnerabilities, open a private GitHub security advisory if
available, or contact the maintainer privately before public disclosure. Include
the affected component, reproduction steps, impact, and any relevant sanitized
artifacts. Do not publish exploit details before a fix is available.

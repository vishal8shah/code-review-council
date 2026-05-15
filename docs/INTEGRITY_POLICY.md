# Integrity Policy

Integrity policy is the safety contract for Code Review Council. The system
must not silently pass when reviewer output, Chair synthesis, transport,
parsing, or reporting loses information needed to trust the verdict.

## What Counts As An Integrity Failure

Integrity failures include:

- Reviewer model output that is not valid JSON after supported parsing fallback.
- Reviewer task exceptions, transport failures, or timeouts.
- More than half of a reviewer's raw findings being malformed and dropped.
- A reviewer returning `FAIL` with no findings and no error.
- Chair transport, parsing, or invalid JSON failure.
- Owner-audience generation that would hide accepted technical findings.
- Reporter drift that drops accepted findings, degraded reasons, or reviewer
  integrity errors from a required output surface.

## Degraded Mode

Degraded mode means the review continued, but at least one integrity signal
reduced trust in the result.

Degraded runs must:

- Set `degraded = true` on the final verdict.
- Preserve sanitized `degraded_reasons`.
- Surface the degraded state in terminal, markdown, JSON, and GitHub PR output
  where those reporters are enabled.
- Reduce confidence or recommend manual review when appropriate.
- Respect configured enforcement, especially `on_integrity_issue = "fail"` in
  CI.

Degraded mode is not a hidden warning. It is part of the verdict contract.

## Invalid Model Output

Reviewer invalid JSON must become a structured reviewer output with:

- `integrity_error = true`
- `output_mode = "failed"` or the relevant attempted mode
- A sanitized error message
- A verdict selected by the configured integrity policy

Chair invalid JSON, transport failure, or parsing failure must fail closed with:

- `verdict = "FAIL"`
- `confidence = 0.0`
- `degraded = true`
- A clear degraded reason
- No fabricated accepted findings

## Dropped Findings

Malformed findings may be dropped only when the drop is visible.

Required behavior:

- Count parsed versus raw findings.
- Surface a reviewer error when malformed findings are dropped.
- Mark the reviewer as an integrity error when the malformed ratio is greater
  than half.
- Use sanitized schema diagnostics such as field names and validation error
  types.
- Do not echo unsafe or long model-generated finding text in diagnostics.

## Reviewer Timeouts And Exceptions

Reviewer failures must produce explicit reviewer outputs instead of disappearing
from the panel.

Required behavior:

- Preserve reviewer id and model.
- Set confidence to `0.0`.
- Include a sanitized `error`.
- Mark `integrity_error = true`.
- Add a degraded reason for Chair synthesis.

## Chair Synthesis And Dissent

The Chair must adjudicate findings, not smooth them away.

Chair rules:

- Evaluate each finding individually.
- Accept, dismiss, downgrade, or upgrade with reasoning.
- Require specific evidence for accepted blockers.
- Preserve serious dissent even if other reviewers passed.
- Dismiss evidence-free or hallucinated findings.
- Never use reviewer count alone as the reason for accepting a blocker.
- Never hide degraded reasons in the summary.

## JSON Reporter Expectations

JSON output is the machine-readable CI contract. It must include:

- `verdict`
- `confidence`
- `chair_output_mode`
- `degraded`
- `degraded_reasons`
- `accepted_blockers`
- `warnings`
- `dismissed_findings`
- Reviewer `error`
- Reviewer `integrity_error`
- Reviewer `output_mode`
- Transport notes when available

JSON output must not convert missing, malformed, or invalid model output into
success.

## GitHub Reporter Expectations

GitHub PR reporting is best-effort reporting, not verdict computation.

Required behavior:

- Emit annotations for capped accepted blockers and warnings.
- Post or update the sticky summary when credentials and PR context allow.
- Best-effort inline comments must deduplicate and sanitize untrusted text.
- GitHub API failure must not alter the review verdict.
- Degraded integrity signals must be visible in the sticky summary when posted.

## Fail Closed, Warn, Or Ignore

Use this policy unless a future design doc explicitly changes it:

| Condition | Policy |
| --- | --- |
| Chair synthesis transport/parsing failure | Fail closed |
| Hardcoded secret with strong evidence | Fail closed |
| CI integrity issue with `on_integrity_issue = "fail"` | Fail closed |
| Reviewer invalid JSON | Degrade and follow integrity enforcement config |
| Reviewer timeout/exception | Degrade and follow integrity enforcement config |
| Dropped findings over threshold | Degrade and follow integrity enforcement config |
| Owner presentation failure | Deterministic fallback, do not drop findings |
| GitHub API/reporting failure | Warn/degrade reporting only, do not change verdict |
| History storage failure during review | Warn only, do not change verdict |
| Explicit history inspection failure | Exit non-zero with user-facing error |

Ignoring an integrity signal is allowed only when the user or config explicitly
chooses that policy and the signal remains visible.

## Required Tests For Integrity Changes

Changes in this area need focused regression coverage for:

- Invalid reviewer JSON.
- Reviewer timeout or task exception.
- Malformed and dropped findings.
- `FAIL` with no findings.
- Chair invalid JSON or transport failure.
- Degraded reasons in terminal, markdown, JSON, and GitHub output.
- Owner presentation fallback preserving every accepted finding.
- CI enforcement when `on_integrity_issue = "fail"`.

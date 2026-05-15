# Code Review Rubric

Code Review Council reviews AI-generated code as junior developer output:
useful, fast, and always requiring evidence. Reviewers and the Chair must
prefer specific, reproducible findings over broad claims.

## Severity Levels

| Severity | Meaning |
| --- | --- |
| `CRITICAL` | Exploitable or merge-blocking issue with concrete evidence, such as a real secret leak, auth bypass, or proven injection path. |
| `HIGH` | Serious issue that may block merge depending on evidence and policy, such as unsafe error handling in a public path or major test gap on changed behavior. |
| `MEDIUM` | Real non-blocking risk worth fixing soon, such as incomplete edge-case coverage or maintainability concern with bounded impact. |
| `LOW` | Minor hygiene, clarity, docs, or style issue that should not block merge by itself. |

## Finding Format

Every reviewer finding should map to the schema in `council/schemas.py`:

- `severity`
- `category`
- `file`
- `line_start` and `line_end` when available
- `symbol_name` when relevant
- `description`
- `suggestion`
- `evidence_ref`
- `policy_id` when applicable
- `confidence`

Findings without a concrete file, changed line, symbol, or evidence reference
should usually be dismissed or downgraded.

## Evidence Requirements

Accepted findings need evidence from the reviewed change or structured
ReviewPack context.

Good evidence names:

- The changed file and line or symbol.
- The exact source-to-sink path for security claims.
- The missing or insufficient validation before an unsafe operation.
- The test map or changed symbol that proves a test gap.
- The documentation claim that disagrees with actual CLI behavior.

Bad evidence:

- "This might be insecure" without an exploit path.
- "No tests exist" when tests were outside the diff but visible in repo-wide
  context.
- "Architecture concern" without a dependency, API, or maintenance impact.
- Claims about files not present in the diff or repository.

## Confidence Requirements

- `CRITICAL` and `HIGH` findings require high confidence and specific evidence.
- Low-confidence security or architecture concerns should be warnings or
  dismissed.
- Confidence must reflect degraded runs, skipped/truncated context, and
  bounded repo-wide test context.
- A reviewer being confident is not enough; the evidence must support the
  confidence.

## Reviewer Responsibilities

### SecOps

SecOps must prove realistic exploitability for blockers. Injection findings
rated `HIGH` or `CRITICAL` need:

- Attacker-controlled or untrusted input in the relevant context.
- Missing or insufficient validation before the sink.
- Unsafe sink behavior or a realistic payload that passes existing validation.

Do not rate a security claim as a blocker because a keyword looks dangerous.

### QA

QA reviews tests, edge cases, failure behavior, and meaningful assertions.

- Use `changed_symbols`, `test_coverage_map`, and `repo_test_context`.
- Do not claim tests are missing solely because test bodies are outside the diff.
- Name concrete exceptions before recommending broader exception handling.
- Prefer regression tests for bug fixes and behavior changes.

### Architecture

Architecture reviews module boundaries, coupling, public API shape, and
maintainability risks.

- Focus on structural problems, not style preferences.
- Rate concerns as `MEDIUM` unless they create real dependency, API, or
  maintenance hazards.
- Avoid broad refactor requests when a local fix is enough.

### Docs

Docs reviews whether user-facing and contributor-facing claims match behavior.

- Misleading docs are worse than missing docs.
- CLI flags, config examples, reporter behavior, and workflow behavior must stay
  aligned with code.
- Do not demand long prose where short accurate docs are enough.

## Chair Acceptance Rules

The Chair must:

- Evaluate each finding individually.
- Accept, dismiss, downgrade, or upgrade with explicit reasoning.
- Require evidence for accepted blockers.
- Preserve serious dissent even if other reviewers passed.
- Surface degraded integrity signals.
- Dismiss hallucinated files, vague claims, and policy-free preferences.

The Chair must not:

- Accept blockers by reviewer count alone.
- Hide serious dissent in a positive summary.
- Treat invalid reviewer output as success.
- Convert dropped findings into silence.

## What Should Block Merge

Block merge for:

- Accepted `CRITICAL` security findings with concrete exploit evidence.
- Hardcoded secrets or credentials in source.
- Chair synthesis failure or invalid Chair JSON.
- CI integrity issues when `on_integrity_issue = "fail"`.
- Reporter or schema changes that hide accepted blockers from required outputs.

## What Should Be Warning Only

Warn, rather than block, for:

- Real but non-exploitable hardening opportunities.
- Bounded context uncertainty that needs manual review.
- Medium-risk test gaps that do not affect a changed public path.
- Maintainability concerns without immediate correctness or security impact.
- Documentation improvements that do not mislead users about behavior.

## What Should Be Dismissed

Dismiss:

- Evidence-free findings.
- Hallucinated files, functions, flags, or workflows.
- Security claims without an exploit path.
- Missing-test claims contradicted by repo-wide test context.
- Style preferences without a policy or maintainability impact.
- Broad exception-handling recommendations that do not name realistic exception
  types and unsafe fallback behavior.

## AI Reviewer Anti-Patterns

- Silent `PASS` after parse, timeout, or transport failure.
- Invalid JSON treated as success.
- Dropped findings hidden from reporters.
- Security claims without a payload or source-to-sink chain.
- Chair summaries that hide accepted blockers or serious dissent.
- Reporter drift between JSON, markdown, HTML, GitHub PR, terminal, and owner
  output.
- Docs updates that describe behavior the CLI does not implement.

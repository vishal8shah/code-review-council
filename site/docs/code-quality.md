# Code Quality

Council's code quality rule is simple: use the smallest clear change that keeps
review integrity obvious. Concise code is good; clever code that hides failure
behavior is not.

## Practical Standard

- Prefer small, reversible changes.
- Reuse existing schemas, helpers, reporters, and config patterns.
- Keep trust-boundary logic explicit.
- Use comments to explain why, not what.
- Add tests that fail without the behavior change.
- Keep docs and workflow examples aligned with real CLI behavior.

## Succinctness

Use fewer lines when doing so removes duplication or clarifies a guard. Do not
compress code when it hides integrity, security, reporting, or error-handling
decisions.

If a condition needs a long explanatory comment, extract a named helper when the
helper makes the invariant clearer.

## Comments

Good comments explain:

- Why a path fails closed.
- Why untrusted input is sanitized or bounded.
- Why compatibility behavior must remain.
- Why a tempting simpler path would hide a review failure.

Avoid comments that restate assignments, loops, or obvious conditionals.

## High-Risk Files

Use extra restraint in `chair.py`, `cli.py`, `orchestrator.py`,
`reviewers/base.py`, `llm_transport.py`, and reporters. These files define the
trust contract users rely on.

When touching them, prefer guard clauses, clear private helpers, and focused
tests over adding more branching to already-large functions.

## Pull Request Checklist

Before merging, confirm:

- The change is as small as it can be while staying readable.
- Comments explain reasoning, not mechanics.
- Tests cover success and important failure modes.
- Reporter and integrity signals are still visible.
- Public docs match CLI and workflow behavior.

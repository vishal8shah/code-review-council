# Code Quality

Code Review Council reviews AI-generated code, so its own code must be boring,
small, and easy to audit. Optimize for the smallest clear change that preserves
the product's integrity contract.

## Quality Bar

- Prefer concise code, but never trade away readability, evidence, or safety.
- Keep changes local unless a broader abstraction clearly removes repeated
  behavior or names an important invariant.
- Reuse existing schemas, helpers, reporters, and config patterns before adding
  new ones.
- Treat integrity, reporting, prompts, and workflow behavior as high-risk code.
- Make behavior easy to test from the outside instead of testing private
  implementation details by default.

## Succinct Code

Shorter code is better only when it remains obvious.

Use fewer lines when that:

- Removes duplication.
- Collapses noisy branching into a clear guard clause.
- Replaces ad hoc parsing with an existing structured helper.
- Keeps the invariant visible at the call site.

Do not compress code when that:

- Hides security or integrity decisions.
- Makes failure behavior harder to see.
- Requires clever Python features that future agents may misuse.
- Combines unrelated responsibilities into one expression.

## Comments

Comments should explain why a decision exists, not repeat what the code says.

Good comments name:

- Integrity or fail-closed reasoning.
- Trust boundaries around untrusted diff, model, config, or GitHub input.
- Non-obvious compatibility behavior.
- Why a simple-looking alternative would be unsafe.

Avoid comments that only narrate assignments, loops, or obvious conditionals.
If a comment is needed to explain a complex condition, prefer a named helper
when that helper makes the invariant clearer.

## Function And Module Shape

High-touch files need extra restraint:

- `council/chair.py`
- `council/cli.py`
- `council/orchestrator.py`
- `council/reviewers/base.py`
- `council/reporters/*`
- `council/llm_transport.py`

When touching these files:

- Prefer guard clauses over nested branching.
- Extract a helper when one function starts mixing validation, transformation,
  transport, and rendering.
- Keep helpers private unless another module genuinely needs the behavior.
- Do not add a helper used once unless it names a real invariant or removes
  meaningful branching.
- Keep tests close to the behavior they protect.

## Test Quality

Tests should prove behavior that matters to users, CI, or agents.

- Regression tests must fail without the change.
- Prefer table-driven tests when scenarios share setup.
- Use full-object assertions when that gives a clearer contract than many
  field-by-field checks.
- Add reporter parity coverage when output fields change.
- Add integrity coverage when reviewer, Chair, transport, schema, or reporter
  behavior changes.

## Review Checklist

Before a PR is ready, answer:

- Is this the smallest clear change that solves the problem?
- Did the change grow a high-risk file when extraction would be clearer?
- Are comments explaining why rather than what?
- Did tests prove the behavior and important failure modes?
- Did docs and generated workflow examples stay aligned with CLI behavior?
- Did reporter parity and integrity visibility remain intact?

# Design

This page summarizes the system architecture and operating model in a web-friendly format.
It is adapted from the full design document, with focus on practical implementation details.

## Contents

1. Architecture overview
2. Why ReviewPack exists
3. The 5-stage pipeline
4. Output modes: developer vs owner
5. Security posture summary
6. CI + BYOK workflow model
7. Cost and latency factors
8. Design constraints and non-goals

---

## 1) Architecture overview

Code Review Council is built as a staged review pipeline rather than a single LLM call.
That design provides two major benefits:

- **Deterministic checks first**: cheap, repeatable checks run before probabilistic analysis.
- **Structured reviewer context**: reviewers consume curated context, not an unbounded raw diff.

At a high level, the system flow is:

1. Deterministic static and policy checks.
2. Diff filtering and token-budget preparation.
3. Structured review package assembly.
4. Parallel specialist reviewer analysis.
5. Chair adjudication and final recommendation.

This decomposition keeps responsibilities clear, improves debuggability, and allows individual
stages to evolve without replacing the whole pipeline.

### Stage boundaries as contracts

Each stage emits explicit artifacts that are consumed by the next stage.
Examples include:

- filtered diff context,
- policy findings,
- reviewer findings and rationale,
- chair-level accepted/dismissed decisions.

By treating stage outputs as contracts, the pipeline is easier to test and reason about.

---

## 2) Why ReviewPack exists

A raw diff is not ideal LLM input by itself.
It can be noisy, incomplete, and expensive to process.

ReviewPack exists to improve reviewer quality by providing:

- changed-file and changed-symbol context,
- policy and gate results,
- supporting snippets relevant to findings,
- constrained, predictable structure across reviews.

### Practical reasons this matters

- **Lower noise**: generated files or lockfile churn can be de-prioritized.
- **Better evidence quality**: reviewers can cite specific context consistently.
- **More stable behavior**: structured prompts reduce random variation in outputs.
- **Budget control**: context can be trimmed to fit model limits.

ReviewPack is therefore a quality and reliability mechanism, not just a packaging convenience.

---

## 3) The 5-stage pipeline

## Stage 1 — Gate Zero

Gate Zero runs deterministic checks (for example, static policy and hygiene checks)
that do not require model inference.

Purpose:

- provide fast fail-fast signals,
- capture objective baseline findings,
- avoid paying model cost for obvious issues.

## Stage 2 — Diff preprocessing

Diff preprocessing reduces irrelevant or low-value input before model analysis.

Typical actions include:

- filtering noisy files,
- handling oversized changes,
- enforcing context/token budget strategy.

Purpose:

- focus reviewer attention on meaningful changes,
- keep latency and token usage predictable.

## Stage 3 — ReviewPack assembly

The system transforms filtered input into structured reviewer context.

ReviewPack can include:

- changed files and symbols,
- gate/policy findings,
- contextual metadata useful to reviewer personas.

Purpose:

- standardize evidence inputs for all reviewers,
- prevent each reviewer from independently re-deriving the same context.

## Stage 4 — Reviewer panel

Specialized reviewer personas (for example SecOps, QA, Architect, Docs)
run in parallel against the same structured context.

Purpose:

- increase coverage through specialization,
- isolate reasoning domains,
- speed up review by parallelizing calls where configured.

## Stage 5 — Chair synthesis

The chair model evaluates panel findings and produces a final recommendation.
The chair is evidence-oriented and can accept, downgrade, or dismiss findings.

Purpose:

- unify conflicting reviewer outputs,
- enforce evidence thresholds,
- produce a single decision artifact for users and CI.

---

## 4) Output modes: developer vs owner

The underlying analysis is shared; output formatting differs by audience.

### Developer output

Developer output emphasizes technical execution details:

- file/line references,
- finding rationale,
- policy/evidence framing for implementation follow-up.

### Owner output

Owner output emphasizes business and product clarity:

- plain-English risk summaries,
- likely impact framing,
- actionable next-step communication.

The two output modes are presentation variants over the same core review results.

---

## 5) Security posture summary

Security decisions are intentionally evidence-driven.

### Secrets policy

When a hardcoded secret is identified with concrete code evidence,
it is treated as a critical blocker.

### Injection policy

Injection findings require an exploitability chain, not just pattern matching.
Expected chain elements include:

1. untrusted input source,
2. insufficient validation/sanitization,
3. unsafe sink and realistic exploit path/payload.

This posture reduces speculative blocker findings and keeps decisions tied to demonstrable risk.

---

## 6) CI + BYOK workflow model

The project supports two primary workflow modes in GitHub Actions.

### PR workflow (repository workflow)

- runs on pull request events,
- can run `--github-pr` behavior when required secrets are available,
- publishes `council-report.json` artifact output.

### BYOK workflow (manual/fork-friendly)

- triggered with workflow_dispatch inputs,
- intended for bring-your-own-key execution in controlled contexts,
- validates ref/repository inputs before review,
- publishes both `council-report.json` and `council-review.md` artifacts.

### Local workflow

Local runs are typically advisory and can write markdown/json outputs to user-selected paths
via CLI flags (for example `--output-md` and `--output-json`).

---

## 7) Cost and latency factors

Cost and latency are configuration- and workload-dependent.
No universal fixed number is valid across all environments.

Primary factors:

- **Model selection** (provider/model families differ),
- **Diff size and complexity** (larger context usually means higher runtime/cost),
- **Reviewer concurrency** (parallelism can reduce wall-clock time but affect burst usage),
- **Retry/timeout behavior** (impacts tail latency and robustness).

Operational guidance:

- start with modest concurrency,
- review smaller diffs when possible,
- tune model mix to balance quality and budget.

---

## 8) Design constraints and non-goals

### Constraints

- deterministic and probabilistic stages must coexist cleanly,
- artifact outputs should remain machine- and human-readable,
- workflow behavior must remain explicit for forks and BYOK usage.

### Non-goals

- claiming bug-free guarantees,
- replacing human code review,
- asserting fixed cost/latency outcomes independent of configuration.

---

## Practical takeaway

Code Review Council is designed as a layered quality gate:

- deterministic checks establish objective baseline quality,
- structured context improves specialist reviewer signal,
- evidence-based chair synthesis yields a single actionable result.

This architecture supports both developer-depth and owner-readable outputs while keeping
enforcement configurable for local and CI environments.

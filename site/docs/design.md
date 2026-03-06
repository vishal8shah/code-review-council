# 🧠 Design

> Council is built as a staged pipeline, not a single LLM call. Each stage has a clear contract, a clear cost, and a clear failure mode. This page explains why.

---

## 🏗️ Architecture at a Glance

The core insight is that most PR quality problems are cheap to detect deterministically. LLM analysis should only run after those checks pass.

```
PR opened
    │
    ▼
┌───────────────────────┐
│  Stage 0: Gate Zero       │  ← deterministic, zero LLM cost, < 2s
└───────────────────────┘
    │ (pass)
    ▼
┌───────────────────────┐
│  Stage 1: Preprocessor    │  ← filter noise, enforce token budgets
└───────────────────────┘
    │
    ▼
┌───────────────────────┐
│  Stage 2: ReviewPack      │  ← build structured reviewer context
└───────────────────────┘
    │
    ▼
┌───────────────────────┐
│  Stage 3: Reviewer Panel  │  ← 4 specialists, parallel, evidence-required
└───────────────────────┘
    │
    ▼
┌───────────────────────┐
│  Stage 4: Chair Synthesis │  ← adjudicate, render verdict
└───────────────────────┘
    │
    ▼
  PASS / FAIL / PASS WITH WARNINGS
```

Each stage emits an explicit artifact consumed by the next. That makes the pipeline testable, debuggable, and evolvable one stage at a time.

---

## 📦 Why ReviewPack Exists

A raw diff is poor LLM input. It's noisy, context-free, and expensive to process at scale.

ReviewPack transforms the diff into structured reviewer context before any model sees it:

| What ReviewPack Adds | Why It Matters |
|----------------------|----------------|
| Changed files + symbol index | Reviewers cite specific locations, not vague references |
| Gate Zero findings | Reviewers don't re-derive known issues |
| Policy violation pre-screen | Evidence is already anchored before model call |
| Token budget enforcement | Predictable cost and latency regardless of diff size |
| Lockfile/generated file exclusions | Reviewer attention goes to human-authored code only |

!!! info "ReviewPack is a quality mechanism, not just packaging"
    Structured prompts produce more stable, auditable outputs than feeding raw diffs. The same ReviewPack format across all reviewers also makes it easier to compare and adjudicate findings.

---

## 🔬 The 5 Stages in Detail

### Stage 0 — Gate Zero

Fast, deterministic, zero LLM cost. Runs in under 2 seconds.

| Check Type | Examples |
|------------|----------|
| Secret detection | Hardcoded API keys, tokens, credentials |
| Static analysis | Lint errors, type check failures |
| Policy hygiene | Missing docstrings, banned imports, file-size limits |
| Diff sanity | Empty diff detection, oversized PR warning |

Gate Zero findings are passed forward into ReviewPack so reviewers don't re-derive them.

### Stage 1 — Diff Preprocessor

Filters the diff before any model sees it:

- Strips lockfiles (`package-lock.json`, `poetry.lock`, `Cargo.lock`, etc.)
- Strips generated files (`*.pb.go`, `*_generated.py`, migration files)
- Enforces per-reviewer token budgets via configurable truncation strategy
- Emits a `--ci --branch` warning if `--branch` is missing (empty diff risk)

### Stage 2 — ReviewPack Assembly

Builds the structured context object passed to all reviewers. One assembly, four consumers.

### Stage 3 — Reviewer Panel

Four specialist agents run in parallel against the same ReviewPack:

| Reviewer | Domain | Evidence Requirement |
|----------|--------|-----------------------|
| 🛡️ SecOps | Vulnerabilities, secrets, injection chains | Full exploit chain |
| 🧪 QA | Test coverage, edge cases, error handling | Specific missing case |
| 🏗️ Architect | Design, coupling, scalability | Concrete code reference |
| 📝 Docs | Completeness, accuracy, clarity | Specific gap identified |

Each reviewer must provide file + line evidence for any finding it raises. Pattern-matching alone is not accepted.

### Stage 4 — Chair Synthesis

The Chair is the adjudication layer. It doesn't just aggregate — it evaluates:

| Chair Action | When Applied | Effect on Verdict |
|--------------|-------------|-------------------|
| **Accept** | Finding has full evidence chain | Included in verdict, may block |
| **Downgrade** | Finding is real but overstated | Becomes a warning, doesn't block |
| **Dismiss** | Finding is speculative or duplicate | Removed from verdict |

Only `FAIL`-level accepted findings block a merge. `PASS WITH WARNINGS` merges through.

!!! warning "Chair is not a majority-vote system"
    One reviewer raising a valid critical finding can cause a `FAIL` even if the other three pass. Equally, three reviewers raising the same speculative finding can all be dismissed. Evidence quality, not reviewer count, determines the verdict.

---

## 📄 Stage Outputs as Contracts

| Stage | Emits | Consumed By |
|-------|-------|-------------|
| Gate Zero | `GateResult` (findings + pass/fail) | ReviewPack, Chair |
| Preprocessor | Filtered diff, token metadata | ReviewPack |
| ReviewPack | `ReviewPack` object | All 4 reviewers |
| Reviewer Panel | 4 × `ReviewerFinding` | Chair |
| Chair | `ChairVerdict` (verdict + rationale + per-reviewer decisions) | CI, artifacts, user |

This contract model means any stage can be replaced, upgraded, or mocked independently.

---

## 💰 Cost & Latency

No universal number is valid — cost and latency depend on configuration and workload. Primary factors:

| Factor | Lower Cost/Latency | Higher Cost/Latency |
|--------|--------------------|---------------------|
| Model selection | GPT-4o-mini for Docs/Arch | GPT-5.2 for all roles |
| Diff size | Small focused PR | Large multi-file refactor |
| Concurrency | Parallel reviewers (default) | Sequential (debugging mode) |
| Retry behavior | Single attempt | Aggressive retry on timeout |

Operational guidance: start with the default model mix, review focused diffs, tune `reviewer_timeout_seconds` if you see tail latency on large PRs.

---

## 🚫 Design Non-Goals

Council is deliberately scoped. These are explicit non-goals:

- **No bug-free guarantee** — Council reviews the diff, not the full codebase
- **No replacement for human judgment** — complex architectural decisions need human context
- **No fixed cost/latency promise** — model selection and diff size dominate
- **No full application security audit** — use a dedicated SAST/DAST tool for that layer
- **No universal reviewer correctness** — degraded mode surfaces failures rather than hiding them

---

## ⏩ Related Pages

- [Security](security.md) — evidence policies, BYOK model, merge gates
- [Workflows](workflows.md) — PR workflow vs BYOK workflow, artifact locations
- [Self Review](self-review.md) — the full pipeline in action on a real PR

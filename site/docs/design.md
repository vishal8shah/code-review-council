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
| Chair | `ChairVerdict` (verdict + rationale + per-reviewer decisions) | Guidance helper, CI, artifacts, user |
| Guidance | Deterministic next steps, fix prompts, verification notes | Terminal, Markdown, HTML, GitHub PR summaries |

This contract model means any stage can be replaced, upgraded, or mocked independently.
Guidance is deterministic on purpose: it reuses the accepted Chair findings and
does not make an extra LLM call or weaken fail-closed CI behavior.

---

## Phase 4B History Contract

The first Phase 4B intelligence slice records local review history before any
autofix work. History uses stdlib SQLite, defaults to the OS user cache, and is
best-effort so storage failures never change review verdicts or CI exit codes.
Configured history paths must be repo-relative and resolve inside the repo;
absolute paths, `~` escapes, and parent traversal are rejected.

With `store_finding_text = false`, finding history stores only `run_id`,
`fingerprint`, `severity`, `category`, `file_path`, `reviewer_id`, `policy_id`,
`verdict`, `is_repeated`, and `debt_run_count`. It never stores raw diff,
evidence, suggestions, diff snippets, fix prompts, Chair reasoning text, or
model-generated descriptions by default.

The database uses `_schema_migrations(version INTEGER PRIMARY KEY, applied_at
TEXT)` for forward-only, idempotent migrations. `council history summary`
surfaces repeat candidates after two runs and labels `[DEBT]` only after three
consecutive runs for the same repo.

Because `council history summary` is explicitly inspecting local storage, it
exits non-zero with a concise error when the database is unavailable, corrupt,
or newer than this Council version supports. Review-mode history writes remain
best-effort and never change verdicts or CI exit codes.

Retention pruning deletes expired run rows and relies on the `findings.run_id`
foreign-key cascade to remove dependent finding rows, keeping cleanup aligned
with the schema contract.

---

## Phase 4C Bounded Test Context

Phase 4C adds bounded full-repo test discovery before any autofix work. Council
scans existing test files for changed source files so reviewers do not treat
tests outside the diff as no tests found.

The scan is controlled by `[context]`, defaults on, respects `.councilignore`,
skips heavy directories such as `.git`, `node_modules`, build/cache folders,
virtual environments, and `*.egg-info`, and caps both file count and file size.
If context is capped or a file cannot be read, the review continues and the
repo-wide context is labeled incomplete.

The existing `test_coverage_map` remains diff-local. Repo-wide matches live in
`ReviewPack.repo_test_context` and are presented as bounded evidence, not proof
of test quality or complete coverage.

---

## Phase 4D Language Analyzer Rollout

Phase 4D graduates the existing TypeScript and JavaScript Gate Zero analyzers
from opt-in to default-on. Python still uses stdlib AST parsing; TypeScript and
JavaScript continue to use parser-free export heuristics for documentation and
type-presence checks. Projects can disable individual languages in
`[gate_zero.analyzers]` when they need a softer rollout.

---

## Cost & Latency

No universal number is valid — cost and latency depend on configuration and workload. Primary factors:

| Factor | Lower Cost/Latency | Higher Cost/Latency |
|--------|--------------------|---------------------|
| Model selection | Smaller models for lower-risk roles | Frontier preview models such as Gemini 3 Pro Preview |
| Diff size | Small focused PR | Large multi-file refactor |
| Concurrency | Parallel reviewers (default) | Sequential (debugging mode) |
| Retry behavior | Single attempt | Aggressive retry on timeout |

Operational guidance: start with the generated defaults, review focused diffs,
and tune `reviewer_timeout_seconds` if you see tail latency on large PRs. The
generated GitHub workflows use Gemini with `reviewer_concurrency = 1` to avoid
preview-model timeout and rate-limit noise.

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

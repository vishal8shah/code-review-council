# 👁️ Overview

> AI tools can now generate code faster than most teams can review it properly. That's exciting. It's also a trust problem that nobody has cleanly solved yet.

---

## 💡 Why This Exists

In 2026, a single developer with Cursor, Copilot, or a custom coding agent can ship PRs faster than a team of five used to. Review capacity hasn't scaled with output capacity. Senior engineers become the bottleneck. Rubber-stamping happens. Unreviewed AI-generated code ships quietly — with bugs, gaps, and sometimes vulnerabilities.

Code Review Council is the automated trust layer built for this reality. It doesn't replace human judgment — it ensures every PR gets a structured, evidence-based review before it reaches a human, so the human's time goes on decisions, not discovery.

---

## 🤖 The Multi-LLM Approach

Council doesn't require a single LLM for everything. The local config is
provider-configurable, while the generated GitHub workflows currently pin every
CI reviewer and the Chair to Gemini for predictable secret handling:

| Role | Domain | Local scaffold default | Generated CI default |
|------|--------|------------------------|----------------------|
| 🛡️ SecOps | Security vulnerabilities, secret detection, injection chains | `openai/gpt-5.2` | `gemini/gemini-3-pro-preview` |
| 🧪 QA | Test coverage, edge cases, error handling | `openai/gpt-5.2` | `gemini/gemini-3-pro-preview` |
| 🏗️ Architect | Design patterns, coupling, scalability | `openai/gpt-4o` | `gemini/gemini-3-pro-preview` |
| 📝 Docs | Documentation completeness, clarity | `openai/gpt-4o-mini` | `gemini/gemini-3-pro-preview` |
| 🪑 Chair | Synthesis, evidence adjudication, final verdict | `openai/gpt-4o` | `gemini/gemini-3-pro-preview` |

This matters for two reasons. First, local teams can distribute blind-spot risk
by assigning different providers or model families to different roles. Second,
they can control cost by using heavier models only where the stakes justify it.
Generated CI currently chooses single-provider reliability instead.

---

## 🔬 The 5-Stage Pipeline

Every PR passes through five stages before a verdict is issued:

| Stage | Name | What Happens |
|-------|------|--------------|
| **0** | Gate Zero | Deterministic checks — secrets, lint, types, missing docs. Zero LLM cost. Under 2 seconds. |
| **1** | Diff Preprocessor | Filters lockfiles and generated code. Enforces token budgets. |
| **2** | ReviewPack Assembly | Builds structured context: changed symbols, test map, policy violations. |
| **3** | Reviewer Panel | 4 specialist agents run in parallel against the same ReviewPack. |
| **4** | Council Chair | Synthesises all findings. Requires exploit chain for blockers. Renders verdict. |

The staged design means cheap deterministic checks run first — only PRs that clear Gate Zero proceed to LLM analysis. This keeps cost and latency predictable.

---

## 🎯 Two Outputs, One Analysis

The same review engine produces two output formats depending on who needs to act:

| Output | Audience | What It Contains |
|--------|----------|------------------|
| 🧑‍💻 **Developer** | Engineers | File/line findings, evidence chains, fix suggestions, fix prompts, next steps, policy references |
| 🧑‍💼 **Owner** | Product / Leadership | Plain-English risk summary, ship/no-ship recommendation, copy-paste fix prompt |

Neither audience gets a weaker review. The analysis is identical — only the presentation changes.

---

## 🔁 The Autonomous Loop Vision

Council was built with a specific end-state in mind: **fully autonomous development with automated quality enforcement at every gate.**

```
AI agent writes code  (e.g. OpenClaw)
        ↓
   PR opened automatically
        ↓
Council reviews — 4 reviewers + Chair
        ↓
  PASS? → merge ✅
  FAIL? → findings fed back to coding agent
        ↓
  Agent patches and resubmits
        ↓
   Council re-reviews
        ↓
 (loop until PASS, then merge)
```

V1 delivered the review gate. V2 expanded ReviewPack parity for Python,
TypeScript, and JavaScript. V3 hardened provider portability, `council doctor`,
and GitHub PR reporting. V4 is split deliberately: V4A starts with onboarding
and deterministic fix guidance, then continues into local/CI parity and full-repo
context planning; V4B adds the intelligence layer such as opt-in autofix,
repeated-debt detection, and metrics.

---

## ✅ What Council Does

- ✅ Runs deterministic checks before any LLM analysis (zero cost fast-fail)
- ✅ Builds structured reviewer context to reduce guesswork and hallucination
- ✅ Uses specialist reviewers in parallel, each on a model matched to their domain
- ✅ Requires a full exploit chain before accepting any security blocker
- ✅ Produces outputs for both technical and non-technical audiences
- ✅ Operates as a CI hard gate or a local advisory tool
- ✅ Surfaces degraded mode explicitly when a reviewer fails — never silently passes

## ❌ What Council Does Not Do

- ❌ Does **not** guarantee bug-free or vulnerability-free software
- ❌ Does **not** replace human engineering judgment on complex architectural decisions
- ❌ Does **not** make universal promises about speed or cost — these depend on model selection, diff size, and concurrency
- ❌ Does **not** audit your entire application — it reviews the **diff**, not the full codebase

!!! warning "Scope reminder"
    Council is a PR/diff/code-change review tool. It is not a full holistic application security audit platform. Use it as one layer in a layered quality strategy.

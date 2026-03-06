# 🏛️ Code Review Council

<div class="hero">
  <p class="hero-tagline">AI reviews AI-generated code. Evidence required. No hallucinated blockers.</p>
  <p>
    <a class="hero-btn hero-btn-primary" href="getting-started/">Get Started →</a>
    <a class="hero-btn" href="https://github.com/vishal8shah/code-review-council">View on GitHub</a>
  </p>
</div>

![AI is writing your code — who is reviewing it?](assets/infographics/hero-ai-writing-whos-reviewing.png)

---

## ⚡ How It Works

Every PR passes through a five-stage pipeline — deterministic checks first, LLM analysis only where it adds value:

| Stage | Name | What Happens | Cost |
|-------|------|--------------|------|
| **0** | 🔒 Gate Zero | Secrets, lint, types, missing docs — under 2 seconds | Zero |
| **1** | ✂️ Diff Preprocessor | Filters lockfiles and generated code, enforces token budgets | Zero |
| **2** | 📦 ReviewPack | Builds structured context: symbols, test map, policy violations | Zero |
| **3** | 🤖 Reviewer Panel | SecOps, QA, Architect, Docs — parallel, evidence required | 4× LLM |
| **4** | 🪑 Council Chair | Synthesises findings, requires exploit chain for blockers, renders verdict | 1× LLM |

![5-stage pipeline and two output modes](assets/infographics/pipeline-5-stage-two-outputs.png)

---

## 🎯 Two Outputs, One Review Engine

| | 🧑‍💻 Developer | 🧑‍💼 Owner |
|---|---|---|
| **Audience** | Engineers | Product / Leadership |
| **Focus** | File/line findings, evidence, fix suggestions | Plain-English risk, ship/no-ship recommendation |
| **Extra** | Policy references, Chair rationale | Copy-paste fix prompt for AI coding agent |
| **Review strength** | Full | Full — same engine, different presentation |

---

## 📊 Real Verdict

This is actual output from Council reviewing its own PR:

```
Overall verdict: PASS  (confidence: 0.90)

  secops     PASS   0 findings
  qa         PASS   2 findings  (2 warnings accepted)
  architect  PASS   0 findings
  docs       PASS   0 findings

Runtime: 48 seconds
```

→ See the full breakdown on the [Self Review](self-review.md) page.

---

## ⚡ Try It in 60 Seconds

```bash
git clone https://github.com/vishal8shah/code-review-council
cd code-review-council
pip install .
council init
council review --branch main
```

!!! warning "Quality gate, not a guarantee"
    Council is not a substitute for human engineering judgment. Cost and latency vary by model and diff size. Use restricted BYOK keys on repos you control.

---

## 🗺️ Explore the Docs

| Page | What You'll Find |
|------|------------------|
| [Overview](overview.md) | Why this exists, the multi-LLM approach, the autonomous loop vision |
| [Getting Started](getting-started.md) | Install, init, first review, CI setup |
| [Design](design.md) | Architecture decisions, ReviewPack, evidence-based Chair |
| [Security](security.md) | BYOK model, key scoping, threat mitigations, merge gates |
| [Workflows](workflows.md) | PR workflow vs BYOK workflow, artifact locations |
| [Self Review](self-review.md) | Council reviewing its own PR — real output, 26 fixes, 44 tests |
| [FAQ](faq.md) | Fork PRs, model config, cost tuning, PR comments |
| [Contributing](contributing.md) | Setup, tests, adding a new reviewer persona |

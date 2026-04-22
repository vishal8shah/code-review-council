# Code Review Council — Solution Design & Architecture

## Executive Summary

The **Code Review Council** is a multi-agent LLM orchestration system that acts as a rigorous, automated quality gate for AI-generated ("vibe-coded") code. Changes pass through a panel of specialized LLM reviewers — each with a distinct persona and review mandate — and a configurable "Council Chair" that synthesizes feedback, resolves conflicts, and renders the final pass/fail verdict. The local scaffold remains provider-configurable; generated GitHub workflows currently pin CI to Gemini via `GOOGLE_API_KEY`.

The system operates at **two enforcement points**: a **CI/PR hard gate** (the primary enforcement mechanism — blocks merge on FAIL) and a **local CLI advisory mode** (fast feedback during development, never blocks push). This dual-mode design ensures the gate cannot be bypassed under pressure while keeping the local developer experience frictionless.

> **Design philosophy**: Policy-driven, evidence-first review. Reviewers consume a structured **Review Pack** (not raw diff text), and every finding must cite specific code evidence. The system is deterministic where possible (Gate Zero), and probabilistic only where judgment is required (LLM reviewers).

---

## 1. Architecture

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DEVELOPER WORKFLOW                           │
│                                                                     │
│   IDE / Claude Code / Cursor / Copilot                              │
│       │                                                             │
│       ▼                                                             │
│   LOCAL: `council review` (advisory — never blocks push)            │
│       │                                                             │
│       ▼                                                             │
│   git push → PR opened                                              │
│       │                                                             │
│       ▼                                                             │
│   CI: GitHub Action / GitLab CI (hard gate — blocks merge on FAIL)  │
│       │                                                             │
│       ▼                                                             │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │              CODE REVIEW COUNCIL ENGINE                      │  │
│   │                                                              │  │
│   │   ┌──────────────┐                                           │  │
│   │   │  Diff Parser  │ ← git diff --staged / branch compare    │  │
│   │   │  & Enricher   │ → AST, symbols, test map, language ID    │  │
│   │   └──────┬───────┘                                           │  │
│   │          │                                                   │  │
│   │          ▼                                                   │  │
│   │   ┌──────────────┐     DIFF PREPROCESSOR                    │  │
│   │   │  Filter &    │ → Ignore patterns, truncation, token     │  │
│   │   │  Budget      │   budgets, generated file detection       │  │
│   │   └──────┬───────┘                                           │  │
│   │          │                                                   │  │
│   │          ▼                                                   │  │
│   │   ┌──────────────┐     PRE-FLIGHT CHECKS (Stage 0)          │  │
│   │   │  Gate Zero   │ → Docstrings? README? Lint? Types?        │  │
│   │   │  (Static)    │ → FAST FAIL — no LLM cost if missing     │  │
│   │   └──────┬───────┘                                           │  │
│   │          │ pass                                               │  │
│   │          ▼                                                   │  │
│   │   ┌──────────────┐     REVIEW PACK ASSEMBLY                 │  │
│   │   │  Build       │ → Diff + symbols + test map + policies   │  │
│   │   │  ReviewPack  │   + Gate Zero results → single object     │  │
│   │   └──────┬───────┘                                           │  │
│   │          │                                                   │  │
│   │          ▼                                                   │  │
│   │   ┌──────────────────────────────────────────────┐           │  │
│   │   │         REVIEWER PANEL (Stage 1)             │           │  │
│   │   │                                              │           │  │
│   │   │  ┌─────────┐ ┌─────────┐ ┌──────────┐       │           │  │
│   │   │  │ SecOps   │ │  QA     │ │  Arch    │       │           │  │
│   │   │  │ Reviewer │ │ Reviewer│ │  Reviewer│  ...  │           │  │
│   │   │  │(Claude)  │ │(Gemini) │ │ (Claude) │       │           │  │
│   │   │  └────┬─────┘ └───┬─────┘ └────┬─────┘      │           │  │
│   │   │       │            │            │             │           │  │
│   │   │       ▼            ▼            ▼             │           │  │
│   │   │  ┌──────────────────────────────────────┐    │           │  │
│   │   │  │   Structured Review Outputs (JSON)   │    │           │  │
│   │   │  └──────────────────┬───────────────────┘    │           │  │
│   │   └─────────────────────┼────────────────────────┘           │  │
│   │                         │                                    │  │
│   │                         ▼                                    │  │
│   │   ┌──────────────────────────────────────────────┐           │  │
│   │   │         COUNCIL CHAIR (Stage 2)              │           │  │
│   │   │         Configurable Chair                  │           │  │
│   │   │                                              │           │  │
│   │   │  • Receives all reviewer verdicts             │           │  │
│   │   │  • Resolves conflicting feedback              │           │  │
│   │   │  • Renders PASS / FAIL / PASS_WITH_WARNINGS  │           │  │
│   │   │  • Generates actionable summary               │           │  │
│   │   └──────────────────┬───────────────────────────┘           │  │
│   │                      │                                       │  │
│   │                      ▼                                       │  │
│   │   ┌──────────────────────────────────────────────┐           │  │
│   │   │         OUTPUT & FEEDBACK (Stage 3)          │           │  │
│   │   │                                              │           │  │
│   │   │  • Terminal report (pass/fail + findings)     │           │  │
│   │   │  • Deterministic next steps + fix guidance    │           │  │
│   │   │  • JSON artifact (for CI integration)         │           │  │
│   │   │  • Markdown review file (.council-review.md)  │           │  │
│   │   │  • PR comment + inline annotations (CI mode)  │           │  │
│   │   └──────────────────────────────────────────────┘           │  │
│   └──────────────────────────────────────────────────────────────┘  │
│       │                                                             │
│       ▼                                                             │
│   LOCAL: Always proceeds (advisory findings printed)                │
│   CI: Merge blocked on FAIL / allowed on PASS or PASS_WITH_WARNINGS│
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Recommended Tech Stack

Given the goal of vibe-coding this quickly, the stack should minimize boilerplate and maximize the ratio of prompting to plumbing:

| Layer | Recommendation | Rationale |
|-------|---------------|-----------|
| **Language** | **Python 3.12+** | Fastest to vibe-code; best LLM SDK ecosystem; your existing fork is Python-based |
| **LLM Orchestration** | **LiteLLM** (unified proxy) | Single interface to call Claude, GPT-4o, Gemini, etc. via OpenAI-compatible API. Eliminates per-provider SDK management. Drop-in replacement for `openai.ChatCompletion.create()` |
| **Async Execution** | **asyncio + `asyncio.gather()`** | Fan-out reviewer calls in parallel — critical for keeping latency under control |
| **Structured Output** | **Pydantic v2** | Define strict review schemas; prefer `response_format` when supported and retry with prompt-only JSON fallback when a provider rejects native JSON mode |
| **Diff Parsing** | **`unidiff`** (Python lib) + `git` subprocess | Parse unified diffs into per-file, per-hunk structured objects |
| **Diff Preprocessing** | **Custom filter/truncation layer** | Ignore patterns (like `.gitignore` for review scope), token budget management, generated file detection, and honest truncation for large diffs |
| **Static Analysis (Gate Zero)** | **Python `ast`** + **dependency-free TS/JS heuristics** | Plugin system for per-language rules. Python uses `ast.parse()`; TypeScript/JavaScript scan exported symbols line-by-line without extra parser dependencies. |
| **Symbol Extraction** | **Python `ast`** + **dependency-free TS/JS export heuristics** + deleted-symbol regex heuristics | ReviewPack extracts Python definitions with `ast.parse()`, TypeScript/JavaScript exports with line-based heuristics, and deleted symbols from diff hunks across languages. |
| **CLI Interface** | **`typer`** | Beautiful CLI with minimal code; auto-generates `--help` |
| **Configuration** | **TOML** (`.council.toml` in repo root) | Human-readable, git-committable config for reviewer personas, thresholds, model assignments |
| **Git Integration** | **GitHub Actions** (primary gate) + local CLI advisory runs | CI blocks merge on FAIL; local runs provide fast advisory feedback |
| **Output/Reports** | **Rich** (terminal) + **Markdown/HTML** (files) + **GitHub PR reporter** (CI) | Pretty terminal output locally; persistent review artifacts; sticky summaries plus inline PR comments in CI |
| **Testing** | **pytest + pytest-asyncio** | Test the council itself — dogfood the QA layer |

### 1.3 Project Structure

```
code-review-council/
├── .council.toml              # Default configuration
├── council/
│   ├── __init__.py
│   ├── cli.py                 # Typer CLI entrypoint
│   ├── config.py              # TOML config loader + Pydantic settings
│   ├── doctor.py              # Preflight diagnostics for repo/model/GitHub setup
│   ├── diff_parser.py         # Git diff → structured DiffContext
│   ├── diff_preprocessor.py   # Filtering, truncation, token budgets
│   ├── review_pack.py         # Assembles ReviewPack from diff + AST + policies
│   ├── gate_zero.py           # Static pre-flight checks (docs, lint, types)
│   ├── guidance.py            # Deterministic fix prompts, verification steps, next-step guidance
│   ├── llm_transport.py       # Shared LiteLLM JSON transport + fallback helpers
│   ├── orchestrator.py        # Fan-out to reviewers, collect, pass to chair
│   ├── reviewers/
│   │   ├── base.py            # BaseReviewer ABC
│   │   ├── secops.py          # Security-focused reviewer
│   │   ├── qa.py              # Test coverage & error handling reviewer
│   │   ├── architecture.py    # Design patterns & complexity reviewer
│   │   ├── docs.py            # Documentation completeness reviewer
│   │   └── custom.py          # User-defined persona loader
│   ├── analyzers/             # Language-specific Gate Zero plugins
│   │   ├── base.py            # BaseAnalyzer ABC + shared test-path helper
│   │   ├── python.py          # Python: docstrings, type hints via ast
│   │   ├── typescript.py      # TypeScript: TSDoc, exports, route docs
│   │   ├── javascript.py      # JavaScript: JSDoc, exports
│   │   └── registry.py        # Maps file extensions → analyzer
│   ├── chair.py               # Configurable Council Chair synthesis
│   ├── schemas.py             # Pydantic models for all structured I/O
│   └── reporters/
│       ├── terminal.py        # Rich console output
│       ├── markdown.py        # .council-review.md generator
│       ├── json_report.py     # Machine-readable JSON output
│       ├── html_report.py     # Standalone HTML report output
│       ├── transport.py       # Shared transport-note helpers for reporters
│       └── github_pr.py       # Sticky PR summary + inline review reporting
├── prompts/
│   ├── secops.md             # System prompt for SecOps persona
│   ├── qa.md                 # System prompt for QA persona
│   ├── architecture.md       # System prompt for Architecture persona
│   └── docs.md               # System prompt for Docs persona
├── .github/
│   └── workflows/
│       └── council-review.yml # GitHub Action (hard gate)
├── tests/
├── pyproject.toml
└── README.md
```

---

## 2. Shift-Left Quality: The Four-Stage Pipeline

The key insight is: **don't waste LLM tokens on issues a linter can catch.** The pipeline is designed as a funnel where cheap, fast checks happen first.

### Stage 0 — Gate Zero (Static Analysis, No LLM Cost)

This is the fastest, cheapest quality gate. It runs in <2 seconds and catches the most common vibe-coding sins before any API call is made.

**Language-Aware Design**: Gate Zero uses a plugin-based analyzer system. The `analyzers/registry.py` maps file extensions to the appropriate analyzer. Python uses `ast.parse()`, while TypeScript/JavaScript use dependency-free exported-symbol heuristics for JSDoc and TypeScript function-signature checks.

**What it checks:**

| Check | Mechanism | Languages | Fail Condition |
|-------|-----------|-----------|----------------|
| **Doc comments present** | AST walk for doc nodes (Python docstrings, TSDoc, JSDoc) | Python, TS, JS | Any public function/class/export missing documentation |
| **README.md updated** | Check if `README.md` is in the diff's changed files list | All | New public API/module added but README not in diff |
| **Type annotations present** | AST walk for type nodes (Python type hints, TS types) | Python, TS | Any public function missing return type or param annotations |
| **No secrets leaked** | Regex patterns for API keys, tokens, passwords in diff content | All | Any match = hard fail |
| **Lint passes** | Run configured linter on changed files (ruff, eslint, etc.) | Configurable | Any error-level lint violation |
| **File size sanity** | Check individual file sizes in diff | All | Single file >1000 lines added (likely AI dump without decomposition) |

**Per-Language Analyzer Examples:**

```python
# analyzers/python.py
class PythonAnalyzer(BaseAnalyzer):
    extensions = [".py"]
    
    def check_docs(self, source: str, file_path: str) -> list[Finding]:
        tree = ast.parse(source)
        # ... walk FunctionDef, ClassDef, check body[0] is Expr(Constant(str))
    
    def check_types(self, source: str, file_path: str) -> list[Finding]:
        # ... check FunctionDef.returns, arg.annotation

# analyzers/typescript.py
class TypeScriptAnalyzer(BaseAnalyzer):
    extensions = [".ts", ".tsx"]
    
    def check_docs(self, source: str, file_path: str) -> list[Finding]:
        # Line-based detection for exported functions/classes lacking JSDoc
        # Only enforces on `export` declarations, not internal helpers
    
    def check_types(self, source: str, file_path: str) -> list[Finding]:
        # Flag exported functions missing explicit return or parameter annotations
```

**Fail behavior:** Gate Zero failures produce an immediate, actionable error message with exact file:line references and skip all LLM stages. This is critical — it means a missing docstring costs the developer 0 API tokens and <1 second of wait time.

```python
# Example Gate Zero output
❌ GATE ZERO FAILED — Fix these before council review:

  [DOCS] src/parsers/xml_handler.py:42 — Function `parse_node()` missing docstring
  [DOCS] src/parsers/xml_handler.py:78 — Function `validate_schema()` missing docstring  
  [TYPES] src/parsers/xml_handler.py:42 — Function `parse_node()` missing return type annotation
  [SECRET] config/dev.env:3 — Possible AWS access key detected (AKIA...)

  4 issues found. Run `council fix` for auto-remediation suggestions.
```

### Stage 0.5 — Diff Preprocessor (Token Budget Management)

Real-world diffs are messy. AI-generated code often touches package-lock.json, includes vendored dependencies, generates large test fixtures, or produces framework boilerplate. Without preprocessing, these blow up token counts and degrade reviewer quality.

The Diff Preprocessor runs after Gate Zero and before ReviewPack assembly:

**What it does:**

| Function | Mechanism | Default Behavior |
|----------|-----------|-----------------|
| **Ignore patterns** | `.councilignore` file (gitignore syntax) | Skip `package-lock.json`, `*.lock`, `*.min.js`, `*.generated.*`, `vendor/`, `dist/`, `node_modules/` |
| **Generated file detection** | Header comment patterns (`// @generated`, `# auto-generated`) + known paths | Exclude from LLM review; flag in report as "skipped" |
| **Token budget enforcement** | tiktoken estimation per file | If total diff exceeds `max_review_tokens` (default: 20,000), truncate lowest-priority files first. Some model mixes may be capped more aggressively in practice to stay below provider request-size limits |
| **File prioritization** | Security-sensitive files first (auth, crypto, API routes), then business logic, then tests, then config/docs | Ensures token budget is spent on highest-risk code |
| **Truncation** | For files exceeding `max_file_tokens` (default: 8,000), truncate to the token limit | Current behavior truncates at the token boundary. Future versions may split at parser-aware function/class boundaries. Truncated files are labeled in the ReviewPack |

**Configuration in `.council.toml`:**

```toml
[preprocessor]
max_review_tokens = 20000          # total token budget for LLM reviewers
max_file_tokens = 8000             # per-file limit before truncation
ignore_file = ".councilignore"     # gitignore-style exclusion patterns

[preprocessor.priorities]
# Higher number = reviewed first when budget is tight
security = 10    # auth.py, crypto.py, middleware.py
business = 7     # core application logic
tests = 4        # test files
config = 2       # configuration, build files
docs = 1         # markdown, comments-only changes
```

### Stage 0.75 — ReviewPack Assembly

This is the critical architectural improvement: **reviewers do not receive raw diff text.** They receive a structured **ReviewPack** — a single Pydantic object containing everything needed for an informed review.

```python
# schemas.py — The ReviewPack

class ChangedSymbol(BaseModel):
    """A function, class, or export that was modified."""
    name: str
    kind: Literal["function", "class", "method", "interface", "type", "export", "route", "schema"]
    file: str
    line_start: int
    line_end: int
    change_type: Literal["added", "modified", "deleted"]
    signature: str | None = None       # e.g., "def parse_node(xml: str) -> Node"
    has_tests: bool = False            # whether a test file references this symbol
    test_file: str | None = None       # path to corresponding test file

class PolicyViolation(BaseModel):
    """A Gate Zero finding passed through to reviewers for context."""
    check: str                         # e.g., "docstring_quality", "type_hint"
    file: str
    line: int | None = None
    message: str
    auto_fixed: bool = False           # was this already remediated by Gate Zero?

class ReviewPack(BaseModel):
    """The canonical input to all LLM reviewers. Assembled once, consumed by all."""
    
    # Diff context
    diff_text: str                     # filtered, preprocessed unified diff
    changed_files: list[str]           # list of all changed file paths
    added_files: list[str]             # newly created files
    deleted_files: list[str]           # removed files
    
    # Enriched context (the key differentiator vs. raw diff)
    changed_symbols: list[ChangedSymbol]   # functions/classes/exports/interfaces/types touched
    test_coverage_map: dict[str, list[str]]  # {source_file: [test_files in this diff]}
    languages_detected: list[str]          # ["python", "typescript", ...]
    
    # Policy context
    gate_zero_results: list[PolicyViolation]  # what Gate Zero found (passed or failed)
    repo_policies: dict[str, Any]            # relevant .council.toml policy settings
    
    # Metadata
    branch: str
    commit_range: str                  # e.g., "abc123..def456"
    total_lines_changed: int
    token_estimate: int                # estimated tokens in the reviewer-visible diff text
    files_truncated: list[str]         # files whose hunks were truncated to fit per-file limits
    files_skipped: list[str]           # files filtered or dropped from diff text before reviewer calls
```

**Why this matters:** Without a ReviewPack, even excellent prompts degrade fast. A SecOps reviewer seeing raw diff text has to infer which functions are public, whether tests exist, and what the repo's security policies are. With a ReviewPack, those facts are explicit. The reviewer can focus on judgment, not context reconstruction. The diff text remains budgeted for model safety, but ReviewPack metadata now comes from the full filtered PR diff so changed tests/docs/config still inform review even when their hunks fall outside the token budget.

### Stage 1 — Reviewer Panel (Parallel LLM Calls)

Each reviewer receives the **same ReviewPack** but evaluates it through a specialized lens. They run in parallel via `asyncio.gather()`.

The ReviewPack is serialized to JSON and included in each reviewer's user message. Reviewers are instructed to reference specific `changed_symbols` entries and `test_coverage_map` data in their findings — this produces evidence-backed, not opinion-based, reviews.

### Stage 2 — Council Chair Synthesis

The Chair receives all reviewer outputs and makes the final call. Details in Section 3.

### Stage 3 — Output & Feedback

Reports are generated in multiple formats simultaneously. The developer sees a Rich terminal summary; a `.council-review.md` is optionally written to the repo for PR context; a JSON artifact is emitted for CI systems. Terminal, Markdown, HTML, and GitHub PR summaries share deterministic next-step guidance. Accepted findings also get copy/paste fix prompts and verification steps derived from the Chair finding, not from a second LLM call.

---

## 3. The Council Chair — Orchestration Design

### 3.1 Why a Dedicated Chair?

The Chair role requires a specific capability profile: synthesizing multiple structured inputs, handling contradictions gracefully, reasoning about severity trade-offs, and producing a clear, authoritative verdict. The architecture is **model-agnostic at the Chair position** — you configure the Chair model in `.council.toml`. The local scaffold currently defaults to `openai/gpt-4o`, while generated GitHub workflows override CI to `gemini/gemini-3-pro-preview`.

### 3.2 Chair System Prompt Structure

The Chair prompt is the most critical prompt in the system. Here's the design:

```markdown
# SYSTEM PROMPT — Council Chair

## Role
You are the Council Chair of a Code Review Council. You receive independent 
reviews from multiple specialized reviewers and must synthesize them into a 
single, authoritative verdict.

## Your Responsibilities
1. **Synthesize** — Identify consensus findings across reviewers
2. **Adjudicate** — When reviewers disagree, reason about which perspective 
   is correct based on the specific code context
3. **Prioritize** — Rank findings by severity (CRITICAL > HIGH > MEDIUM > LOW)
4. **Verdict** — Render exactly one of: PASS, PASS_WITH_WARNINGS, FAIL
5. **Justify** — Every verdict must include a clear rationale

## Verdict Process (Evidence/Policy-Based, NOT Count-Based)
You do NOT use mechanical counting rules like "3+ HIGH = FAIL". Instead:

1. **Triage each finding**: For every finding from every reviewer, you must 
   explicitly ACCEPT it as a blocker or DISMISS it with a stated reason.
2. **Require evidence**: A finding is only accepted as a blocker if it includes 
   a concrete `evidence_ref` (file, line range, symbol, diff hunk). Findings 
   without evidence are automatically downgraded to advisory.
3. **Check policy alignment**: Gate Zero policy violations that were passed 
   through to reviewers are first-class inputs. If a reviewer's finding 
   reinforces a Gate Zero policy violation, it carries more weight.
4. **Apply severity logic**:
   - **FAIL**: Any accepted CRITICAL blocker (security-validated or policy-backed)
   - **PASS_WITH_WARNINGS**: Accepted HIGH/MEDIUM findings that are non-blocking
   - **PASS**: No accepted blockers
5. **Chair adjudication policy**: Secrets exposures are auto-escalated to 
   CRITICAL blockers when validated in changed code. Prompt-injection findings 
   require an exploitability chain (source, sink, and execution path) and are 
   not auto-accepted without that evidence.

## Conflict Resolution Rules
- If reviewers disagree on severity, examine the evidence quality of each 
  position. Better-evidenced findings win.
- If 2+ reviewers independently flag the same issue with evidence, this 
  strengthens the finding but does not mechanically upgrade severity.
- A single-reviewer HIGH finding may still be accepted as a blocker if the 
  evidence is compelling and policy-aligned.
- Dismiss findings that are stylistic preferences without policy backing.

## Input Format
You will receive a JSON array of reviewer outputs. Each contains:
- `reviewer_id`: The reviewer persona name
- `model`: The LLM model used
- `verdict`: Their individual PASS/FAIL recommendation
- `findings`: Array of {severity, category, file, line, description, suggestion}
- `confidence`: 0.0-1.0 self-assessed confidence

## Output Format (strict JSON)
{
  "verdict": "PASS" | "PASS_WITH_WARNINGS" | "FAIL",
  "confidence": 0.0-1.0,
  "degraded": false,
  "degraded_reason": null,
  "summary": "2-3 sentence executive summary",
  "accepted_blockers": [
    {
      "severity": "CRITICAL|HIGH",
      "category": "security|testing|architecture|documentation|performance|style",
      "file": "path/to/file.py",
      "line_start": 42,
      "line_end": 55,
      "symbol_name": "parse_node",
      "symbol_kind": "function",
      "description": "Clear description of the issue",
      "suggestion": "Specific fix recommendation",
      "evidence_ref": "ReviewPack.changed_symbols[2] shows no test coverage; diff hunk 3 shows unvalidated input",
      "policy_id": "security.input_validation",
      "source_reviewers": ["secops", "qa"],
      "accept_reason": "Why this is a valid blocker"
    }
  ],
  "dismissed_findings": [
    {
      "original_severity": "HIGH",
      "category": "style",
      "file": "path/to/file.py",
      "description": "Original finding description",
      "source_reviewer": "architect",
      "dismiss_reason": "Stylistic preference; no policy violation; no evidence of defect"
    }
  ],
  "warnings": [
    {
      "severity": "MEDIUM|LOW",
      "category": "...",
      "file": "...",
      "description": "...",
      "suggestion": "..."
    }
  ],
  "reviewer_agreement_score": 0.0-1.0,
  "rationale": "Detailed reasoning for the verdict"
}
```

### 3.3 Reviewer-to-Chair Data Flow

```python
# schemas.py — Pydantic models enforce structure at every boundary

class Finding(BaseModel):
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    category: Literal["security", "testing", "architecture", "documentation", "performance", "style"]
    file: str
    line_start: int | None = None
    line_end: int | None = None
    symbol_name: str | None = None          # e.g., "parse_node"
    symbol_kind: Literal["function", "class", "method", "interface", "type", "export", "route", "schema"] | None = None
    diff_hunk_id: int | None = None         # index into ReviewPack diff hunks
    description: str
    suggestion: str
    evidence_ref: str | None = None         # explicit reference to ReviewPack data
    policy_id: str | None = None            # e.g., "security.input_validation"
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)

class ReviewerOutput(BaseModel):
    reviewer_id: str
    model: str
    verdict: Literal["PASS", "FAIL"]
    findings: list[Finding]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    tokens_used: int
    error: str | None = None
    integrity_error: bool = False

class ChairVerdict(BaseModel):
    verdict: Literal["PASS", "PASS_WITH_WARNINGS", "FAIL"]
    confidence: float = Field(ge=0.0, le=1.0)
    degraded: bool = False                     # true if integrity issues occurred
    degraded_reasons: list[str] = []
    summary: str
    accepted_blockers: list[Finding]           # findings accepted as blockers (cause FAIL)
    dismissed_findings: list[DismissedFinding] # findings explicitly dismissed with reason
    warnings: list[Finding]                    # non-blocking findings
    reviewer_agreement_score: float
    rationale: str
```

### 3.4 Orchestration Flow (orchestrator.py)

```python
async def run_council(diff_context: DiffContext, config: CouncilConfig) -> ChairVerdict:
    # Stage 0: Gate Zero (deterministic static checks)
    gate_result = gate_zero.check(diff_context, config)
    if gate_result.hard_fail:
        return gate_result.as_early_exit()
    
# Stage 0.5: Diff Preprocessing (filter, truncate, budget)
    processed_diff = diff_preprocessor.process(
        diff_context,
        ignore_file=config.preprocessor.ignore_file,
        max_tokens=config.preprocessor.max_review_tokens,
        max_file_tokens=config.preprocessor.max_file_tokens,
    )
    
    # Stage 0.75: Assemble ReviewPack (structured context for all reviewers)
    review_pack = ReviewPack.assemble(
        diff=processed_diff,
        gate_zero_results=gate_result.findings,
        config=config,
    )
    
    # Stage 1: Fan-out to all reviewers in parallel (same ReviewPack)
    # Use return_exceptions=True for graceful degradation
    reviewer_tasks = [
        reviewer.review(review_pack) 
        for reviewer in config.active_reviewers
    ]
    results = await asyncio.gather(*reviewer_tasks, return_exceptions=True)
    
    # Separate successful reviews from failures
    reviewer_outputs: list[ReviewerOutput] = []
    failed_reviewers: list[str] = []
    for reviewer, result in zip(config.active_reviewers, results):
        if isinstance(result, Exception):
            failed_reviewers.append(f"{reviewer.id}: {type(result).__name__}")
        else:
            reviewer_outputs.append(result)
    
    # Determine degraded status
    degraded = len(failed_reviewers) > 0
    
    # Stage 2: Chair synthesis (with degraded-mode context)
    chair = Chair(model=config.chair_model)
    verdict = await chair.synthesize(
        review_pack=review_pack,
        reviews=reviewer_outputs,
        degraded=degraded,
        failed_reviewers=failed_reviewers,
    )
    # Chair reduces confidence when degraded; in CI, only Gate Zero or 
    # Chair failure blocks merge — missing reviewers don't collapse the run.
    
    # Stage 3: Report (terminal + markdown + PR annotations in CI mode)
    for reporter in config.reporters:
        await reporter.emit(verdict, reviewer_outputs, review_pack)
    
    return verdict
```

---

## 4. Documentation Enforcement — Technical Mechanism

Documentation enforcement operates at **two layers**, which is the key design decision:

### Layer 1: Gate Zero (Deterministic, Zero Cost)

This is the hard gate. It's static-analysis-based, not LLM-based, which means it's fast, free, and un-gameable. The analyzer plugin system keeps the policy interface consistent across languages, even though the current implementations use different parsing strategies.

```python
# analyzers/base.py — All analyzers implement this interface

class BaseAnalyzer(ABC):
    extensions: list[str]  # e.g., [".py"] or [".ts", ".tsx"]
    
    @abstractmethod
    def check_docs(self, source: str, file_path: str) -> list[Finding]: ...
    
    @abstractmethod
    def check_types(self, source: str, file_path: str) -> list[Finding]: ...
    
    def check_all(self, source: str, file_path: str) -> list[Finding]:
        findings = []
        findings.extend(self.check_docs(source, file_path))
        findings.extend(self.check_types(source, file_path))
        return findings

# analyzers/python.py — Python-specific checks

class PythonAnalyzer(BaseAnalyzer):
    extensions = [".py"]
    
    def check_docs(self, source: str, file_path: str) -> list[Finding]:
        """Check that all public functions and classes have docstrings."""
        findings = []
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # Skip private/dunder methods (except __init__)
                if node.name.startswith('_') and node.name != '__init__':
                    continue
                
                has_docstring = (
                    node.body 
                    and isinstance(node.body[0], ast.Expr) 
                    and isinstance(node.body[0].value, ast.Constant) 
                    and isinstance(node.body[0].value.value, str)
                )
                
                if not has_docstring:
                    findings.append(Finding(
                        severity="CRITICAL",
                        category="documentation",
                        file=file_path,
                        line=node.lineno,
                        description=f"{'Class' if isinstance(node, ast.ClassDef) else 'Function'} "
                                    f"`{node.name}()` is missing a docstring",
                        suggestion="Add a docstring describing purpose, params, and return value"
                    ))
        return findings

# analyzers/typescript.py — TypeScript-specific checks

class TypeScriptAnalyzer(BaseAnalyzer):
    extensions = [".ts", ".tsx"]
    
    def check_docs(self, source: str, file_path: str) -> list[Finding]:
        """Check that exported functions/classes have TSDoc comments."""
        # Uses line-based export detection
        # Only enforces on `export` declarations — internal helpers are exempt
        # Checks for /** JSDoc */ preceding export function/class
        ...
    
    def check_types(self, source: str, file_path: str) -> list[Finding]:
        """Check for missing exported function annotations."""
        # Flags exported functions missing explicit parameter or return types
        ...

# analyzers/registry.py — Routes files to the right analyzer

ANALYZER_REGISTRY: dict[str, type[BaseAnalyzer]] = {}

def get_analyzer(file_path: str) -> BaseAnalyzer | None:
    ext = Path(file_path).suffix
    analyzer_class = ANALYZER_REGISTRY.get(ext)
    return analyzer_class() if analyzer_class else None
```

```python
# gate_zero.py — README check (language-agnostic)

def check_readme_updated(diff_context: DiffContext) -> list[Finding]:
    """If new public modules/endpoints are added, README must be in the diff."""
    new_public_modules = [
        f for f in diff_context.added_files 
        if not Path(f).name.startswith('_') 
        and any(f.endswith(ext) for ext in ['.py', '.ts', '.js', '.go', '.rs'])
        and 'test' not in f.lower()
    ]
    
    readme_modified = any(
        'readme' in f.lower() for f in diff_context.changed_files
    )
    
    if new_public_modules and not readme_modified:
        return [Finding(
            severity="HIGH",
            category="documentation",
            file="README.md",
            description=f"New public modules added ({', '.join(new_public_modules)}) "
                        f"but README.md was not updated",
            suggestion="Update README.md to document new modules/APIs"
        )]
    return []
```

### Layer 2: Docs Reviewer (LLM-Based Quality Check)

Gate Zero catches *presence*. The Docs Reviewer catches *quality*. A function might have a docstring that says `"""Does stuff."""` — Gate Zero passes it, but the Docs Reviewer flags it.

```markdown
# SYSTEM PROMPT — Documentation Reviewer

## Role
You are a documentation quality reviewer. You evaluate whether code 
documentation is accurate, complete, and useful — not just present.

## What You Check
1. **Docstring quality**: Does it describe what the function does, its 
   parameters, return values, exceptions raised, and edge cases?
2. **Inline comments**: Are complex algorithms or non-obvious logic explained?
3. **README accuracy**: If README was modified, does it accurately reflect 
   the code changes?
4. **API documentation**: Are new endpoints, CLI commands, or public interfaces 
   documented with usage examples?
5. **Changelog**: For significant changes, is there a changelog entry?

## Severity Guide
- CRITICAL: Docstring is actively misleading (describes wrong behavior)
- HIGH: Public API function has no meaningful documentation
- MEDIUM: Docstring exists but is incomplete (missing params, return type)
- LOW: Minor formatting issues, typos in comments
```

### Configuration in `.council.toml`

```toml
[documentation]
require_docs = true                   # Gate Zero hard requirement (language-aware)
require_type_annotations = true       # Gate Zero hard requirement (language-aware)
require_readme_update_on_new_module = true
require_changelog = false             # optional per-project

[documentation.python]
docstring_style = "google"            # google | numpy | sphinx
min_docstring_length = 20             # chars — catches "Does stuff."
enforce_on = "public"                 # public | all

[documentation.typescript]
enforce_tsdoc_on_exports = true       # TSDoc on exported functions/classes
enforce_route_docs = true             # require docs on changed API routes
flag_any_abuse = true                 # flag explicit `any` types on exports

[documentation.exemptions]
paths = ["tests/", "scripts/", "migrations/", "fixtures/"]
patterns = [
    "test_*",
    "conftest.py",
    "__tests__/",
    "*.spec.ts",
    "*.spec.tsx",
    "*.test.ts",
    "*.test.tsx",
    "*.spec.js",
    "*.spec.jsx",
    "*.test.js",
    "*.test.jsx",
]
```

---

## 5. Reviewer Persona Design

### 5.1 Default Personas

Each reviewer has a tuned system prompt, a designated model, and a focused review scope. Here's the recommended default panel:

| Persona | Local Scaffold Default | Generated CI Default | Focus | Rationale |
|---------|------------------------|----------------------|-------|-----------|
| **SecOps** | `openai/gpt-5.2` | `gemini/gemini-3-pro-preview` | Injection, auth flaws, secrets, dependency risks, input validation | Strong at pattern recognition and security reasoning |
| **QA Engineer** | `openai/gpt-5.2` | `gemini/gemini-3-pro-preview` | Test coverage gaps, error handling, edge cases, assertion quality | Benefits from broad code/test context |
| **Architect** | `openai/gpt-4o` | `gemini/gemini-3-pro-preview` | SOLID violations, coupling, complexity, API design, tech debt indicators | Deep reasoning about structural implications |
| **Docs Reviewer** | `openai/gpt-4o-mini` | `gemini/gemini-3-pro-preview` | Docstring quality, README accuracy, comment usefulness | Lower-risk role that can use cheaper local models when desired |

> **Phase 3 Note:** Multi-provider configurations are supported via LiteLLM, and the Chair/reviewer models are configurable per repository. The generated GitHub Actions workflows intentionally write a temporary Gemini config in CI so the default hosted path needs only `GOOGLE_API_KEY`.

### 5.2 Custom Personas

Users can define additional personas in `.council.toml`:

```toml
[[reviewers]]
id = "performance"
name = "Performance Engineer"
model = "gemini/gemini-3-pro-preview"
prompt = "prompts/performance.md"        # relative to repo root
focus = ["algorithmic complexity", "memory allocation", "N+1 queries", "caching"]
enabled = true
```

---

## 6. Feasibility Assessment

### 6.1 Is This Possible? — Yes, Unequivocally

Every component here exists and is proven:

| Component | Maturity | Notes |
|-----------|----------|-------|
| Multi-model LLM calls via LiteLLM | Production-grade | Used by thousands of projects; supports 100+ providers |
| Structured JSON output from LLMs | Production-grade | Native JSON mode is common but not universal; Council now retries with prompt-only JSON fallback and surfaces the transport mode in reports |
| Git diff parsing | Trivial | `unidiff` library + `git diff` subprocess |
| AST-based code analysis | Built into Python stdlib | `ast.parse()` has been stable for 15+ years |
| GitHub Actions | Standard CI platform | Generated workflows run the hard gate and BYOK path |
| Parallel async API calls | Standard Python | `asyncio.gather()` |

### 6.2 Estimated Build Effort (Vibe-Coding)

Since you're vibe-coding this, here's a realistic timeline:

| Phase | Effort | What You Get |
|-------|--------|-------------|
| **MVP (Weekend sprint)** | 8-12 hours | CLI that parses diffs, calls 2 reviewers in parallel, Chair synthesizes, terminal output |
| **Gate Zero + Analyzers** | 4-6 hours | Static checks with Python AST analysis plus dependency-free TypeScript/JavaScript analyzer plugins |
| **Diff Preprocessor** | 3-4 hours | Ignore patterns, token budgets, truncation, generated file detection |
| **ReviewPack Assembly** | 3-4 hours | Symbol extraction, test map, policy context — the structured reviewer input |
| **Polish** | 4-6 hours | Rich terminal UI, markdown report output, `.council.toml` config |
| **CI Integration** | 3-4 hours | GitHub Action YAML, `--ci` mode, PR summaries, inline comments, and artifacts |
| **Total MVP** | ~25-36 hours | Fully functional Code Review Council with dual-mode enforcement |

Note: The estimate increased from the original ~20-25 hours because we added the diff preprocessor, ReviewPack, and language-agnostic analyzers. These components are worth the extra effort — they prevent the "raw diff + good prompt" degradation that kills review quality at scale.

### 6.3 Cost Estimate Per Review

Cost depends on the configured provider, model tier, diff size, retry behavior,
and whether reviewers run concurrently or sequentially. Assuming an average diff
of ~500 lines across 5-10 files **after preprocessing** (generated files,
lockfiles, and vendored code excluded), each reviewer receives roughly the same
budgeted ReviewPack and the Chair receives the synthesized reviewer outputs.

**Real-world cost caveats:** Without the diff preprocessor, costs can blow up
3-5x due to package-lock changes, vendored dependencies, generated files, large
test fixtures, and framework boilerplate. The preprocessor's token budget
enforcement caps reviewer-visible diff size, while ReviewPack metadata still
surfaces skipped tests/docs/config context.

Generated CI currently favors reliability over speed/cost: it pins all roles to
`gemini/gemini-3-pro-preview`, sets `reviewer_concurrency = 1`, and uses larger
timeouts. Local configs can choose cheaper models for lower-risk roles.

### 6.4 Latency Profile

| Stage | Expected Latency |
|-------|-----------------|
| Gate Zero (static) | < 2 seconds |
| Diff Preprocessing | < 1 second |
| ReviewPack Assembly | < 2 seconds (Python AST + parser-free TS/JS exports + deleted-symbol heuristics) |
| Reviewer Panel (parallel) | 8-15 seconds (bounded by slowest model) |
| Chair Synthesis | 5-10 seconds |
| Report Generation | < 1 second |
| **Total** | **17-31 seconds** |

**Latency caveats:** Large diffs may trigger more truncation and less reviewer-visible code context. In CI mode, latency is less critical than deterministic fail-closed behavior. For local advisory mode, the preprocessor's aggressive filtering keeps most reviews practical.

---

## 7. End-to-End User Experience

### 7.1 First-Time Setup

```bash
# Install
pip install code-review-council

# Initialize in your repo
cd your-project/
council init
# Creates .council.toml with sensible defaults
# Creates .council/prompts/ with default persona prompts
# Creates .councilignore with common exclusion patterns
# Creates .github/workflows/council-review.yml (CI hard gate)
# Creates generated GitHub Actions workflows for CI review

# Set API keys (one-time)
# Generated GitHub workflows use Gemini:
export GOOGLE_API_KEY=...

# Optional for local configs that reference these providers:
export ANTHROPIC_API_KEY=sk-...
export OPENAI_API_KEY=sk-...
```

### 7.2 Daily Workflow — Local Advisory

The local CLI is advisory-only by default. It gives you fast feedback without blocking your workflow.

```bash
# You've been vibe-coding with Claude Code for an hour...
# Quick check before pushing:

$ council review

🏛️  Code Review Council — Reviewing 7 files, 342 lines changed
  ℹ️  Skipped 2 files (package-lock.json, dist/bundle.min.js)
  ℹ️  Token budget: 12,400 / 20,000

  Stage 0: Gate Zero ........... ✅ PASSED (1.2s)
  ReviewPack assembled: 5 changed symbols, 2 with tests
  Stage 1: Reviewer Panel
    ├─ SecOps (gemini/gemini-3-pro-preview) ... ✅ PASS (0 findings)
    ├─ QA (gemini/gemini-3-pro-preview) ....... ⚠️  FAIL (2 findings)
    ├─ Architect (gemini/gemini-3-pro-preview)  ✅ PASS (1 finding)
    └─ Docs (gemini/gemini-3-pro-preview) ..... ✅ PASS (0 findings)
  Stage 2: Chair Synthesis (gemini/gemini-3-pro-preview) ... done

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  VERDICT: ⚠️  PASS WITH WARNINGS (advisory — push not blocked)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  HIGH  [testing] src/parsers/xml_handler.py:42
        Function `parse_node()` has no error handling for malformed XML input.
        No corresponding test covers the malformed-input path.
        Evidence: changed_symbols shows parse_node() with has_tests=false
        → Add try/except for xml.etree.ElementTree.ParseError and a test case.

  MEDIUM [architecture] src/parsers/xml_handler.py:78
        `validate_schema()` has cyclomatic complexity of 14 (threshold: 10).
        → Consider extracting validation sub-steps into helper functions.

  Review saved to: .council-review.md
  💡 These findings will be enforced in CI when you open a PR.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Push always proceeds in advisory mode
$ git push origin feature/new-parser
```

### 7.3 CI Enforcement — The Real Gate

When a PR is opened, the GitHub Action runs the council as a **required status check**. This is the primary enforcement point — it cannot be bypassed with `--no-verify`.

```yaml
# .github/workflows/council-review.yml (generated by `council init`)
name: Code Review Council
on: [pull_request]
jobs:
  council-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install .
      - name: Write CI Gemini config
        run: |
          cat > .council.toml <<'EOF'
          [council]
          chair_model = "gemini/gemini-3-pro-preview"
          timeout_seconds = 360
          reviewer_timeout_seconds = 360
          reviewer_concurrency = 1

          [[reviewers]]
          id = "secops"
          name = "Security Operations Reviewer"
          model = "gemini/gemini-3-pro-preview"
          prompt = "prompts/secops.md"
          enabled = true

          [[reviewers]]
          id = "qa"
          name = "QA Engineer"
          model = "gemini/gemini-3-pro-preview"
          prompt = "prompts/qa.md"
          enabled = true

          [[reviewers]]
          id = "architect"
          name = "Solutions Architect"
          model = "gemini/gemini-3-pro-preview"
          prompt = "prompts/architecture.md"
          enabled = true

          [[reviewers]]
          id = "docs"
          name = "Documentation Reviewer"
          model = "gemini/gemini-3-pro-preview"
          prompt = "prompts/docs.md"
          enabled = true
          EOF
      - run: council review --ci --github-pr --branch ${{ github.base_ref }} --output-json council-report.json
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: council-report
          path: council-report.json
```

In `--ci` mode, the council posts a sticky PR summary, emits workflow annotations, and best-effort inline PR review comments for accepted findings with file/line evidence, then sets the GitHub check status based on the verdict.

### 7.4 On Hard Failure (CI)

```bash
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  VERDICT: ❌ FAIL — Merge blocked
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  CRITICAL [security] src/api/auth.py:23
           SQL query built via string concatenation with user input.
           This is a SQL injection vulnerability.
           Evidence: changed_symbols shows handle_login() modified;
                     no parameterized query pattern detected
           → Use parameterized queries: cursor.execute("SELECT * FROM users 
             WHERE id = %s", (user_id,))

  Merge blocked. Fix CRITICAL issues and push again.
  The CI check will re-run automatically on new commits.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 7.5 Escape Hatch

For genuine emergencies (production down, hotfix needed now):

```bash
# Use GitHub repo admin override:
# "Merge without waiting for requirements" — logged, auditable
# This is the only bypass mechanism in V1.
# A dedicated `--emergency-bypass` CLI flag may be added in a future
# release once the gate has earned trust and false-positive rates are low.
```

---

## 8. Configuration Reference (`.council.toml`)

```toml
[council]
chair_model = "openai/gpt-4o"       # local scaffold default; CI workflow overrides to Gemini
fail_on = "FAIL"                    # FAIL | PASS_WITH_WARNINGS
timeout_seconds = 60                # Chair / owner-summary timeout
reviewer_timeout_seconds = 60       # per-reviewer timeout
reviewer_concurrency = 2            # lower this for slow/rate-limited providers

[council.enforcement]
mode = "ci"                         # ci | local | both
ci_block_on = "FAIL"               # verdict that blocks PR merge
local_mode = "advisory"            # advisory (never blocks) | gate (blocks push)
# CI is the primary enforcement point; local is for fast feedback

[preprocessor]
max_review_tokens = 20000          # total token budget for LLM reviewers
max_file_tokens = 8000             # per-file limit before truncation
ignore_file = ".councilignore"     # gitignore-style exclusion patterns
detect_generated = true            # auto-skip files with @generated headers

[preprocessor.priorities]
security = 10                      # auth, crypto, middleware files
business = 7                       # core application logic
tests = 4                          # test files
config = 2                         # configuration, build files
docs = 1                           # markdown, comments-only changes

[gate_zero]
require_docs = true                # language-aware doc enforcement
require_type_annotations = true    # language-aware type enforcement
require_readme_on_new_module = true
check_secrets = true
max_file_lines = 1000

[gate_zero.linters]
python = "ruff check --diff"
typescript = "eslint --format json"
javascript = "eslint --format json"
# Add per-language lint commands

[gate_zero.analyzers]
# Enable/disable per-language analyzers
python = true
typescript = false    # implemented — enable explicitly when ready
javascript = false    # implemented — enable explicitly when ready

[[reviewers]]
id = "secops"
name = "Security Operations Reviewer"
model = "openai/gpt-5.2"
prompt = "prompts/secops.md"
enabled = true

[[reviewers]]
id = "qa"
name = "QA Engineer"
model = "openai/gpt-5.2"
prompt = "prompts/qa.md"
enabled = true

[[reviewers]]
id = "architect"
name = "Solutions Architect"
model = "openai/gpt-4o"
prompt = "prompts/architecture.md"
enabled = true

[[reviewers]]
id = "docs"
name = "Documentation Reviewer"
model = "openai/gpt-4o-mini"
prompt = "prompts/docs.md"
enabled = true

[reporters]
terminal = true
markdown = true                     # writes .council-review.md
json_report = "ci"                   # auto-write in CI; configurable for local runs
github_pr = false                    # enable with `--github-pr` for sticky summary + inline GitHub reporting

[cost]
warn_threshold_usd = 1.00           # warn if single review exceeds this
budget_daily_usd = 20.00            # hard stop for daily spend
```

---

## 9. Phased Roadmap

### V1 — MVP (Build This First)

Everything described in this document up to this point. The core deliverable:

1. **Typer CLI** with `council init`, `council review`, `council review --ci`
2. **Gate Zero** with language-aware analyzer plugins (Python + TypeScript + JavaScript)
3. **Diff Preprocessor** with ignore patterns, token budgets, and honest truncation
4. **ReviewPack** assembly from enriched diff context
5. **4 reviewer personas** (SecOps, QA, Architect, Docs) running in parallel
6. **Configurable Chair** with structured adjudication
7. **Pydantic schemas** enforcing structure at every boundary
8. **Output**: terminal (Rich), markdown (.council-review.md), JSON
9. **GitHub Actions** as the primary CI gate, plus local advisory CLI runs

### V2 — ReviewPack Parity + Hardening (Implemented)

1. **Python/TypeScript/JavaScript ReviewPack parity** — parser-free TS/JS export extraction plus Python AST extraction.
2. **Shared test-path logic** — Gate Zero and ReviewPack reuse the same test-file classification.
3. **Diff-local support context** — skipped tests/docs/config still surface to reviewers through ReviewPack metadata.
4. **Owner/developer presentation support** — same underlying verdict, different audience output.
5. **Expanded regression coverage** — analyzer, ReviewPack, reporter, and owner-output behavior covered by tests.

### V3 — Portability + PR Usability (Implemented)

1. **Shared JSON transport helper** — reviewer, Chair, and owner-presentation calls use one LiteLLM path.
2. **Structured-output portability** — native JSON mode first, prompt-only fallback on provider rejection, surfaced in report metadata.
3. **`council doctor`** — preflight checks for repo state, branch targets, provider keys, likely fallback-only models, and GitHub PR context.
4. **Transport-aware reporting** — terminal, markdown, HTML, JSON, and GitHub PR summaries show transport notes when fallback or failure occurs.

### V4A — Docs, Onboarding, and Safer Self-Serve Defaults

The next phase starts by reducing setup friction before adding more autonomy:

1. **Docs-first consistency** — keep README, Getting Started, design docs, and site docs aligned on provider defaults, GitHub workflow behavior, and local/CI parity.
2. **Stronger fix guidance** — make developer and owner reports clearer about what to change, what to test, and when a human engineer should review the patch.
3. **Safer self-serve defaults** — keep fail-closed CI integrity behavior, document Gemini workflow requirements, and make `council doctor` the standard first-run diagnostic.
4. **Full-repo context expansion plan** — design repository-wide test/context discovery without pretending the current diff-local map already does it.

### V4B — Intelligence Layer

Only after onboarding and parity are solid:

1. **Auto-fix generation** (`council review --fix`) — opt-in patch generation for CRITICAL/HIGH findings, followed by an automatic re-review. **Prerequisite**: stable verdicts, low false positives, and good evidence quality.
2. **Learning loop** — store review verdicts and findings in a DB. Analyze patterns over time: "80% of your FAIL verdicts are missing error handling in parsers" → surface as pre-review tips.
3. **Repeated-debt detection** — flag issues that keep recurring across PRs.
4. **Confidence calibration** — track Chair verdict accuracy over time, tune conflict resolution weights.
5. **Observability** — push council metrics such as latency, pass/fail rates, cost per review, finding categories, and degraded-run causes to a metrics backend.

---

## 10. Key Design Decisions & Trade-offs

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| **Gate Zero before LLM** | Saves 100% of LLM cost on trivially fixable issues | Requires maintaining static analysis rules per language |
| **ReviewPack over raw diff** | Reviewers get structured context (symbols, tests, policies) — produces evidence-backed findings instead of opinion-based ones | Extra assembly step (~2s); TS/JS coverage mapping still relies on diff-local import and filename heuristics |
| **CI as primary gate, local as advisory** | CI cannot be bypassed with `--no-verify`; local advisory keeps dev experience frictionless | Findings surface later (at PR time vs push time); requires CI secrets setup |
| **Diff preprocessor with token budgets** | Prevents cost blowup from lockfiles, generated code, vendored deps; ensures token budget spent on highest-risk files | May miss issues in truncated/skipped files; requires tuning ignore patterns |
| **Language-aware analyzer plugins** | Same policy interface works for Python, TS, JS, Go, Rust without forcing one parser strategy on every language | More upfront work per language; heuristic analyzers trade parser precision for zero extra dependencies |
| **Parallel reviewers** | ~4x faster than sequential | Higher burst API usage; need rate limit handling |
| **Structured JSON output** | Deterministic parsing; no regex on natural language | Slightly more complex prompts; some models less reliable at strict JSON |
| **Chair as separate stage** | Clean separation; Chair sees all context; adjudicates rather than summarizes | Extra API call adds ~5-10s latency and ~$0.08 cost |
| **LiteLLM over raw SDKs** | Single interface for all providers | Adds a dependency; slight abstraction overhead |
| **TOML config over CLI flags** | Git-committable; team-shareable; self-documenting | Need to write a config loader |
| **Auto-fix deferred to V4B** | Need stable verdicts and low false positives first; auto-fixing hallucinated issues is worse than no auto-fix | Users fix issues manually until the evidence pipeline is trustworthy enough |

### Revision History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2025-02-27 | Initial design |
| v1.1 | 2025-02-28 | Added ReviewPack schema, diff preprocessor, language-agnostic Gate Zero, CI-first enforcement, real-world cost/latency caveats. Incorporated feedback from GPT-4o comparative review. |
| v1.2 | 2025-02-28 | 5 pre-build adjustments: evidence/policy-based Chair (not count-based), enriched Finding schemas with evidence_ref/symbol/confidence, forced JSON in CI mode, degraded-mode handling for reviewer timeouts, removed emergency bypass from V1. |
| v1.3 | 2025-02-28 | Post-implementation update. Two rounds of peer review, 26 fixes applied. Key changes: Chair default GPT-4o (configurable), reviewer defaults updated to OpenAI model mix (configurable), deleted symbol detection via hunk scanning, unified degraded-mode with `degraded_reasons`, linter integration implemented (`shlex.split`, `{files}` placeholder), `repo_policies` populated from config, file boundary headers in diff text, `warnings` as first-class ChairVerdict field, path traversal protection, honest truncation (not "chunking"). 62 tests. See SELF-REVIEW.md for remaining known limitations. |
| v1.4 | 2026-04-11 | Phase 2 and Phase 3 update. ReviewPack now covers Python plus parser-free TypeScript/JavaScript exports, shared test-path classification is reused across Gate Zero and ReviewPack, LiteLLM transport now retries without native JSON mode when providers reject `response_format`, reports surface `output_mode` / transport notes, `council doctor` was added for preflight checks, and GitHub PR reporting now combines sticky summaries with best-effort inline comments. |
| v1.5 | 2026-04-22 | Post-PR #12 docs baseline. GitHub workflows are documented as Gemini-pinned via `GOOGLE_API_KEY`, reviewer timeout and concurrency knobs are part of the config reference, Windows-safe terminal and lossless diff ingestion hardening are captured, and the Phase 4 roadmap is split into V4A onboarding/parity and V4B intelligence. 286 tests collected. |

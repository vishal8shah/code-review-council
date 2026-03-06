# 🥋 Self-Review

> Code Review Council reviewed its own pull request.
> Verdict: **PASS — confidence 0.90 — in 48 seconds.**
> This page documents what that means, what was fixed to get here, and what's still honest work-in-progress.

---

## 📊 The Real Verdict

This is the actual output from Council reviewing its own docs + config PR:

```
Overall verdict: PASS  (confidence: 0.90)

Reviewer panel:
  secops     PASS   0 findings
  qa         PASS   2 findings
  architect  PASS   0 findings
  docs       PASS   0 findings

Accepted warnings:
  [LOW] site/docs/stylesheets/extra.css:1
        No tests present for CSS assets.
        Accepted: expected for documentation-only changes.
        Suggestion: rely on existing MkDocs CI build + consider HTML validation step.

  [LOW] .github/workflows/pages.yml:1
        Bash validation step can fail deploy if infographic assets are missing.
        Accepted: intentional release gate.
        Suggestion: scope to main branch only, document requirement prominently.

Runtime: 48s
```

The two warnings were accepted — not dismissed — because they were real observations with valid rationale. This is the evidence-based Chair model working as intended: findings are adjudicated individually, not counted.

---

## 🔄 Three Rounds of Review

This project went through **two self-review rounds and two GPT-5.2 peer review rounds** before reaching V1. 26 issues were identified and fixed across those rounds.

### Round 1 — Self-Review Fixes

| # | Issue Found | Fix Applied |
|---|-------------|-------------|
| 1 | Secret detection line numbers off | Proper target line tracking through hunk content |
| 2 | `.councilignore` loaded from cwd, not repo root | `repo_root` passed through from orchestrator |
| 3 | No LLM retry logic | `num_retries=2` on all LLM calls |
| 4 | Signature extraction only handled `ast.Name` | `ast.unparse()` for all annotation types |
| 5 | `fnmatch` imported inside loop | Moved to module-level import |

### Round 1 — Peer Review Fixes (GPT-5.2)

| # | Issue Found | Fix Applied |
|---|-------------|-------------|
| 6 | Gate Zero results missing from reviewer/Chair prompts | Full context serialized to both |
| 7 | `changed_symbols` included ALL file symbols, not just changed lines | Filtered to changed line ranges; methods classified |
| 8 | Diff text lost file boundaries | `=== FILE: path (change_type) ===` headers added |
| 9 | No `warnings` field in schema | First-class in schema, parsing, and all reporters |
| 10 | Chair pseudo-JSON schema | Replaced with valid JSON example object |
| 11 | Malformed findings silently dropped | Tracked count, sets error field |
| 12 | `_file_priority()` ignored config | Reads `config.priorities` correctly |
| 13 | Path traversal in `get_file_content()` | `is_relative_to()` containment check added |
| 14 | `--ci` without `--branch` empty diff risk | Warning emitted |
| 15 | Stray brace-expansion directory in repo | Removed |
| 16 | Linter integration config-only, not implemented | Implemented with `shlex.split`, `{files}` placeholder, timeout/error handling |
| 17 | TS/JS analyzers enabled but not implemented | Disabled in default config with honest note |
| 18 | `council init` missing workflow scaffold | Now creates `.github/workflows/council-review.yml` |
| 19 | "Chunking" naming implied splitting — actually truncation | Documented honestly as truncation |

### Round 2 — Peer Review Fixes (GPT-5.2)

| # | Issue Found | Fix Applied |
|---|-------------|-------------|
| 20 | Workflow template assumed PyPI publication | Changed to `pip install .` |
| 21 | Degraded mode only caught asyncio exceptions | Unified: exceptions + invalid JSON + malformed findings all trigger degraded |
| 22 | `degraded_reasons` not visible to users | Added `degraded_reasons: list[str]` to ChairVerdict, propagated through all return paths, surfaced in reporters |
| 23 | Deleted symbols invisible to reviewers | `_extract_deleted_symbols()` scans removed hunk lines for function/class defs |
| 24 | Linter command used `.split()` — unsafe for quoted paths | `shlex.split()` + `{files}` placeholder support |
| 25 | `repo_policies` always empty — config never flowed through | Populated from config: require_docs, require_types, check_secrets, max_file_lines, enabled_analyzers |
| 26 | `github_pr` config defaulted true with no implementation | Set to `false` with explicit comment |

### Post Round 2 — Hardening

| Change | Summary |
|--------|----------|
| Chair injection policy | Removed hard override; added full exploitability evidence gate before any blocker is accepted |
| Prompt guardrails | Additional SecOps and QA guardrails to reduce speculative findings |
| BYOK workflow | Fork-safe workflow emitting `council-report.json` and `council-review.md` artifacts |
| Config schema + defaults | `load_config()` accepts nested `[[council.reviewer]]` / `[[council.reviewers]]`; model mix updated to GPT-5.2/GPT-4o/GPT-4o-mini |

---

## ✅ What's Solid

- **Pipeline stage contracts** — `DiffContext → GateZeroResult → ReviewPack → ReviewerOutput[] → ChairVerdict` — each stage emits an explicit artifact consumed by the next
- **Pydantic v2 schema enforcement** at every stage boundary — no silent failures
- **Unified degraded mode** — if a reviewer times out or returns malformed output, Council continues at reduced confidence and surfaces specific reasons
- **Gate Zero is zero-cost** — deterministic checks with real linter integration, no LLM spend
- **Token budget management** — configurable priorities, truncation labeled honestly
- **Evidence-based Chair** — accept / dismiss / warn three-bucket model; no count-based rules
- **Changed AND deleted symbol detection** — reviewers see what was removed, not just what was added
- **Policy context flows end-to-end** — config settings reach reviewers and Chair
- **Path traversal protection** and CI safety warnings built in
- **44 tests across all modules, all passing**

---

## ⚠️ Remaining Known Limitations

!!! warning "These are documented honestly, not hidden"
    V1 Alpha ships with known limitations. They are tracked, not papered over.

### Accuracy

- **Test coverage map searches diff files only** — labeled `IN DIFF` in prompts. Full repo search is deferred.
- **Test coverage matching is substring-based** — false positives possible on short filenames.
- **Deleted symbol detection is a regex heuristic** — catches `def`/`class` patterns, not complex multiline signatures.
- **`parse_diff` always runs `get_current_branch` subprocess** — unnecessary overhead in test/CI.

### Not Yet Implemented

- **Logical chunking** — large files are truncated, not split at function boundaries. Documented as truncation.
- **`response_format` fallback** — no fallback for models that don't support JSON mode (e.g. some Gemini variants).
- **GitHub PR inline annotations** — disabled by default. Scoped to V2.
- **Editable prompts without code changes** — prompts are in code. V2 scope.

### Design Note

!!! info "One deliberate design disagreement"
    A peer reviewer recommended compact JSON transport for reviewer payloads. We use markdown with all fields present. Rationale: LLMs consume readable structured text more effectively than nested JSON blobs. The information is complete; the format is optimised for the consumer. This is a design choice worth revisiting with real-world false-positive data.

---

## 💡 The Meta Point

Council reviewed its own PR and produced a real, structured verdict with evidence. It didn't hallucinate security blockers. It accepted two low-severity warnings with documented rationale. It ran in 48 seconds across 4 specialist reviewers.

That's not a marketing claim. That's the output. You can see it on the PR.

> *"Not 'trust the AI.' Verify the AI. With another AI. With evidence."*

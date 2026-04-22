# Code Review Council — Self-Review (Post Phase 4A Guidance Slice)

Updated after initial self-review, two rounds of GPT-5.2 peer review, Phase 2
ReviewPack parity, the Phase 3 portability / PR usability merge, and the first
Phase 4A onboarding / fix-guidance slice.

---

## All Fixed Issues

### Round 1 Self-Review Fixes
| # | Issue | Fix |
|---|-------|-----|
| 1 | Secret detection line numbers off | Proper target line tracking through hunk content |
| 2 | `.councilignore` loaded from cwd | `repo_root` passed through from orchestrator |
| 3 | No LLM retry logic | `num_retries=2` on all LLM calls |
| 4 | Signature extraction only handled `ast.Name` | `ast.unparse()` for all annotations |
| 5 | `fnmatch` imported inside loop | Module-level import |

### Round 1 Peer Review Fixes
| # | Issue | Fix |
|---|-------|-----|
| 6 | Gate Zero results not in reviewer/Chair prompts | Full context serialized to both |
| 7 | `changed_symbols` included ALL file symbols | Filtered to changed line ranges; methods classified |
| 8 | Diff text lost file boundaries | `=== FILE: path (change_type) ===` headers |
| 9 | No `warnings` field | First-class in schema, parsing, all reporters |
| 10 | Chair pseudo-JSON schema | Valid JSON example object |
| 11 | Malformed findings silently dropped | Tracked count, sets error field |
| 12 | `_file_priority()` ignored config | Reads `config.priorities` |
| 13 | Path traversal in `get_file_content()` | `is_relative_to()` containment check |
| 14 | `--ci` without `--branch` empty diff risk | Warning emitted |
| 15 | Stray brace-expansion directory | Removed |
| 16 | Linter integration config-only | Implemented with `shlex.split`, `{files}` placeholder, timeout/error handling |
| 17 | TS/JS analyzer placeholders existed without implementation | Shipped dependency-free TS/JS Gate Zero analyzers; kept default-off for an explicit rollout |
| 18 | `council init` missing workflow scaffold | Now creates `.github/workflows/council-review.yml` |
| 19 | "Chunking" naming dishonesty | Documented as truncation |

### Round 2 Peer Review Fixes
| # | Issue | Fix |
|---|-------|-----|
| 20 | Workflow template assumed PyPI publication | Changed to `pip install .` |
| 21 | Degraded mode only checked asyncio exceptions | Unified: exceptions + invalid JSON + malformed findings all set degraded |
| 22 | `degraded_reasons` not visible | Added `degraded_reasons: list[str]` to ChairVerdict, propagated through all return paths, surfaced in terminal/markdown reporters |
| 23 | Deleted symbols invisible to reviewers | `_extract_deleted_symbols()` scans removed hunk lines for function/class defs |
| 24 | Linter command used `.split()` | `shlex.split()` + `{files}` placeholder support |
| 25 | `repo_policies` always empty | Populated from config: require_docs, require_types, check_secrets, max_file_lines, enabled_analyzers |
| 26 | `github_pr` config defaulted true with no implementation | Set to `false` with comment |

---


### Recent Changes (Post Round 2)
| Change | Summary |
|---|---|
| Chair injection policy | Removed hard override for injection findings; added exploitability evidence gate before blocker acceptance |
| Prompt guardrails | Added additional secops and QA guardrails to reduce speculative findings |
| BYOK workflow | Added fork-safe BYOK workflow that emits `council-report.json` and `council-review.md` artifacts |
| Config schema + defaults | `load_config()` now accepts nested `[[council.reviewer]]` / `[[council.reviewers]]`; default reviewer model mix updated to GPT-5.2/GPT-4o/GPT-4o-mini |
| Phase 2 ReviewPack parity | ReviewPack and Gate Zero now cover Python plus parser-free TypeScript/JavaScript symbol and test-path heuristics |
| Phase 3 transport + PR reporting | Shared LiteLLM JSON transport falls back from native JSON mode to prompt-only JSON, `council doctor` preflights setup, and GitHub PR reporting posts sticky summaries plus best-effort inline comments |
| Phase 3 Windows/Gemini hardening | Git diff ingestion preserves undecodable bytes with `surrogateescape`, terminal output sanitizes legacy-console text, generated GitHub workflows pin Gemini with `GOOGLE_API_KEY`, and reviewer timeouts are configurable |
| Phase 4A guidance/onboarding | `council init` and `council doctor` now surface next steps, and terminal/Markdown/HTML/GitHub reports share deterministic fix prompts, verification steps, and review next steps |

---

## Remaining Known Limitations

### Accuracy
- **Test coverage map only searches diff files** — labeled "IN DIFF" in prompts. Full repo search deferred.
- **Test coverage matching is substring-based** — false positives on short filenames.
- **Deleted symbol detection is regex heuristic** — catches `def`/`class` patterns, not multiline signatures.
- **`parse_diff` still performs git subprocess work** — useful in real runs, but some test/CI paths could avoid redundant probes.

### Not Yet Implemented
- **Logical chunking** — Large files truncated, not split at function boundaries. Documented honestly.
- **Full-repo test coverage discovery** — Coverage mapping still works from the diff, not a repository-wide index.
- **Local/CI parity and full-repo context planning** — Remaining Phase 4A work after the guidance/onboarding slice.
- **Learning loop / repeated-debt detection** — Phase 4B scope after onboarding and local/CI parity are smoother.
- **Autofix generation** — Deferred until verdict quality and evidence quality stay stable enough to avoid auto-fixing hallucinated issues.
- **Prompts in code** — Works but not editable without code changes.

### Design Disagreement with Peer Reviewer
- **Reviewer payload format** — Peer reviewer recommends compact JSON transport. We use markdown with all fields present. Rationale: LLMs consume readable text more effectively than nested JSON blobs. The information is complete; the format is optimized for the consumer. We acknowledge this is a design choice worth revisiting with real-world false-positive data.

---

## What's Solid
- Pipeline architecture with clear stage contracts (DiffContext → GateZeroResult → ReviewPack → ReviewerOutput[] → ChairVerdict)
- Pydantic schema enforcement at every boundary
- Unified degraded mode with specific reasons surfaced to users
- Gate Zero is zero-cost with real linter integration
- Token budget management with configurable priorities
- Evidence-based Chair with accept/dismiss/warnings three-bucket model
- Changed AND deleted symbol detection
- Policy context from config flows to reviewers and Chair
- Path traversal protection, CI safety warnings
- Honest about what's implemented vs. claimed
- 300 collected tests across all modules

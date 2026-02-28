# Code Review Council — Self-Review (Post Round 2)

Updated after initial self-review, two rounds of GPT-5.2 peer review, and three hardening passes.

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
| 17 | TS/JS analyzers enabled but not implemented | Disabled in default config |
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

## Remaining Known Limitations

### Accuracy
- **Test coverage map only searches diff files** — labeled "IN DIFF" in prompts. Full repo search deferred.
- **Test coverage matching is substring-based** — false positives on short filenames.
- **Deleted symbol detection is regex heuristic** — catches `def`/`class` patterns, not multiline signatures.
- **`parse_diff` always runs `get_current_branch` subprocess** — unnecessary in test/CI.

### Not Yet Implemented
- **Logical chunking** — Large files truncated, not split at function boundaries. Documented honestly.
- **`response_format` model fallback** — No fallback for models that don't support JSON mode.
- **GitHub PR annotation reporter** — Config disabled by default. V2 scope.
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
- 44 tests across all modules, all passing

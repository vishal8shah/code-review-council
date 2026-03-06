# 🛡️ Security

> Council is designed to be evidence-driven, not pattern-reactive. This page explains the security model for both the tool itself and the code it reviews.

---

## 🔑 Your Keys, Your Control (BYOK)

Code Review Council is a **bring-your-own-key** system. There are no shared API keys, no centralised inference, and no data sent to any Council-operated service.

When you run Council:

- Your code diff is sent **directly from your CI runner to your chosen LLM provider** (OpenAI, Anthropic, etc.)
- Council itself never sees, stores, or forwards your keys or your code
- Your API keys live in **GitHub Actions secrets** on your own repository — not in this project
- If you fork this repo, your keys stay in your fork's secret store

!!! success "The short version"
    Your code never leaves your CI runner except to go directly to the LLM provider you configured. Council is the orchestration layer, not a data handler.

---

## 🔐 API Key Hardening

Not all API keys are equal. Council is designed to work with **restricted, least-privilege keys**.

Recommended key scoping:

| Provider | What Council needs | What to restrict |
|----------|--------------------|------------------|
| OpenAI | `chat.completions` (read) | No fine-tuning, no file upload, no billing access |
| Anthropic | `messages` (read) | No admin, no model management |
| Google | `generativelanguage` inference only | No project admin, no storage |

!!! warning "Only run on repos you control"
    BYOK keys should be used only on branches and repositories you own or have explicit authority to review. The BYOK workflow validates `BASE_REF` and `UPSTREAM_REPO` inputs before resolving any git refs.

---

## 🧯 BYOK Threat Model

The primary threat surface for BYOK usage is **workflow input injection** — where an attacker supplies a malicious `base_ref`, `upstream_repo`, or similar parameter to redirect the review or exfiltrate data.

Council mitigates this with:

- **Input validation** on all workflow dispatch inputs (`BASE_REF`, `UPSTREAM_REPO`)
- **`git check-ref-format`** validation before resolving any target ref
- **`is_relative_to()` containment check** on all file content reads — prevents path traversal outside the repo root
- **`shlex.split()` for linter commands** — prevents shell injection via config-supplied commands
- **`--ci` + `--branch` safety warning** — emitted if `--ci` is passed without an explicit branch (empty diff risk)

!!! danger "Fork PRs and secrets"
    Fork PRs do not have access to repository secrets by design (GitHub's security model). The PR workflow detects this and skips the LLM review step cleanly, uploading a `council-report.json` that explains the skip. **Do not work around this.** Use the BYOK workflow for fork contributor reviews instead.

---

## 🔍 Evidence-Based Review Policy

The most common failure mode in automated security review is **speculative blocking** — raising a finding because a pattern matched, without proving the finding is actually exploitable.

Council's Chair is hardened against this:

### Secrets Policy

A hardcoded secret is only accepted as a **critical blocker** when:
- There is concrete code evidence (file + line reference)
- The value is not a placeholder, example, or test fixture
- The exposure path is clear

### Injection Policy

An injection finding requires a **full exploitability chain** before it blocks a merge:

| Step | Required Evidence |
|------|------------------|
| 1 | Untrusted input source identified |
| 2 | Insufficient validation or sanitisation demonstrated |
| 3 | Unsafe sink identified with realistic exploit path or payload |

All three must be present. Pattern-matching alone — e.g. "this function accepts user input" — is **not sufficient** to block.

!!! info "Why this matters"
    Speculative security blockers erode trust in automated review faster than false negatives do. A tool that cries wolf on every PR gets disabled. Council is designed to raise fewer, higher-confidence findings that engineers actually act on.

---

## 🚨 Merge Gates

Council can operate in two enforcement modes:

| Mode | Command | Behaviour |
|------|---------|----------|
| **Advisory** | `council review` (local) | Never blocks a push. Output only. |
| **Hard gate** | `council review --ci` | Exits non-zero on `FAIL`. Blocks merge in CI. |

The CI gate only blocks on `FAIL`. `PASS WITH WARNINGS` merges through — warnings are documented, not enforced.

---

## 🛠️ Degraded Mode

If a reviewer times out, returns malformed output, or fails to parse, Council does not silently pass or fail. It:

- Continues with the remaining reviewers
- Reduces the confidence score
- Surfaces **specific degraded reasons** to the user via `degraded_reasons` in the ChairVerdict
- Makes the integrity issue visible in CI logs and JSON artifacts via per-reviewer `error` and `integrity_error` fields

This means a partial failure is always visible and auditable, not hidden behind a clean-looking PASS.

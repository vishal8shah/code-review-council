# 🧑‍💻 Contributing

> Contributions welcome. This page covers everything from first setup to opening a PR that gets merged fast.

---

## 🛠️ Dev Environment Setup

### 1. Clone and install (editable)

```bash
git clone https://github.com/vishal8shah/code-review-council
cd code-review-council
pip install -e ".[dev]"
```

Editable install means your local changes take effect immediately — no reinstall needed.

### 2. Verify

```bash
council --version
pytest -q
```

All tests should pass on a clean checkout. If they don’t, open an issue before doing anything else.

### 3. API keys for integration tests

Unit tests are fully mocked and run without any API keys. Integration tests require at least one provider key:

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
```

!!! tip "Use cheap models for local integration testing"
    Set reviewer models to `gpt-4o-mini` in `.council.toml` for local integration runs. No need to burn GPT-5.2 credits on a test diff.

---

## 🧪 Tests

### Running tests

```bash
# All tests (unit only, no API calls)
pytest -q

# With integration tests (requires API keys)
pytest -q --integration

# Specific test file
pytest tests/test_chair.py -v

# With coverage
pytest --cov=council --cov-report=term-missing
```

### Test categories

| Category | Location | Requires Keys? | What’s Covered |
|----------|----------|----------------|----------------|
| Unit | `tests/unit/` | No | Pipeline stages, parsing, validation logic |
| Integration | `tests/integration/` | Yes | End-to-end review runs against real models |
| Fixtures | `tests/fixtures/` | No | Sample diffs, ReviewPacks, mock verdicts |

### Test expectations for PRs

- New features must include unit tests
- Bug fixes must include a regression test that fails before the fix and passes after
- New reviewer personas must include at least one unit test covering output schema compliance
- Coverage should not decrease on the changed module

---

## 🤖 Adding a Reviewer Persona

This is the most common contribution type. Here’s the full walkthrough:

### Step 1 — Write the prompt

Create a prompt file in `prompts/`:

```
prompts/
  secops.md       ← existing
  qa.md           ← existing
  architect.md    ← existing
  docs.md         ← existing
  yourpersona.md  ← new
```

Your prompt must:

- Define the reviewer's domain clearly
- Require file + line evidence for every finding
- Reject speculative findings (no pattern-match-only blockers)
- Produce output compatible with the `ReviewerFinding` schema

### Step 2 — Register in `.council.toml`

```toml
[reviewers.yourpersona]
enabled = true
model = "gpt-4o"
prompt_file = "prompts/yourpersona.md"
```

### Step 3 — Verify schema compatibility

The reviewer output must deserialise cleanly into `ReviewerFinding`. Run:

```bash
pytest tests/unit/test_reviewer_schema.py -v
```

### Step 4 — Add tests

- One unit test with a mock diff → mock LLM response → assert parsed finding structure
- One test asserting the reviewer rejects a finding that has no evidence chain
- One test for the degraded mode path (reviewer returns malformed output)

### Step 5 — Open a PR

See the PR standards below.

!!! info "Naming convention"
    Reviewer IDs in `.council.toml` should be lowercase, single-word (e.g. `secops`, `qa`, `perf`, `accessibility`). The Chair refers to reviewers by their ID in the verdict output.

---

## 📥 Opening a PR

### PR checklist

- [ ] Editable install works cleanly (`pip install -e ".[dev]"`)
- [ ] All unit tests pass (`pytest -q`)
- [ ] New behaviour has test coverage
- [ ] `.council.toml` changes are documented in the PR description
- [ ] Prompt changes include a before/after example in the PR description
- [ ] No hardcoded API keys, tokens, or secrets anywhere in the diff

### What makes a PR get merged fast

| Signal | Why it matters |
|--------|----------------|
| Clear scope | Reviewers understand what changed and why in 30 seconds |
| Test evidence | No guessing whether the fix actually works |
| Small diff | Easier to review, faster to merge |
| Linked issue | Context is captured, not buried in Slack |
| No scope creep | One PR, one concern |

### PR title format

```
type(scope): short description
```

Examples:

```
feat(reviewer): add performance reviewer persona
fix(chair): dismiss speculative injection findings without exploit chain
docs(faq): add cost reduction lever table
test(gate-zero): add regression for empty diff false positive
```

---

## 🐛 Opening an Issue

### Bug reports

Include:

1. What you ran (exact command)
2. What you expected
3. What happened (paste the relevant output or `council-report.json` fields)
4. Your `.council.toml` reviewer/model config (redact keys)

### Feature requests

Describe the use case first, not the implementation. A good feature request looks like:

> _"When reviewing a large PR, I want Council to flag which files were skipped due to token budget so I know what wasn’t covered."_

Not:

> _"Add a `--show-skipped` flag."_

### Known good issue labels

| Label | Meaning |
|-------|---------|
| `good first issue` | Self-contained, well-scoped, good for new contributors |
| `prompt-tuning` | Improvements to reviewer or Chair prompts |
| `false-positive` | A finding that should have been dismissed |
| `false-negative` | A real issue Council missed |

---

## ⏩ Related Pages

- [Design](design.md) — understand the pipeline before adding to it
- [Security](security.md) — evidence requirements that apply to new reviewer personas
- [FAQ](faq.md) — model config, degraded mode, custom personas

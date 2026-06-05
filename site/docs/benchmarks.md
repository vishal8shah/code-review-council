# Benchmarks And Seeded PRs

Council needs repeatable proof that its reviewers find real risks, dismiss
evidence-free claims, and surface degraded model behavior. Seeded PRs are the
first step toward that benchmark suite.

## Current Fixture

| Fixture | Risk | Expected Verdict | Purpose |
| --- | --- | --- | --- |
| `agentic-login-bypass` | Authorization bypass from an AI-agent shortcut | `FAIL` | Proves Council can identify attacker-controlled request parameters in a changed authorization path. |

Fixture path:

```text
benchmarks/seeded-prs/agentic-login-bypass/
```

Each fixture contains:

- `base/`: safe repository state.
- `head/`: risky AI-generated state.
- Sample source files stored as inert `.py.txt` files so this repository does
  not introduce live vulnerable Python code.
- `expected-findings.json`: expected verdict, evidence, and non-goals.
- `README.md`: scenario-specific setup and interpretation notes.

The Council repository excludes `benchmarks/seeded-prs/` from its own LLM review
scope because these fixtures intentionally contain risky sample diffs. Use the
fixtures in a throwaway demo repository when you want Council to review them.

## How To Use A Fixture

Create a temporary repo from `base/`, commit it, copy `head/` over the top, then
run Council against `main`:

```bash
mkdir council-seeded-demo
cp -R benchmarks/seeded-prs/agentic-login-bypass/base/. council-seeded-demo/
cd council-seeded-demo
find . -name '*.py.txt' -exec sh -c 'for path do mv "$path" "${path%.txt}"; done' sh {} +
git init
council init
git add .
git commit -m "seed safe invoice access"

cp -R ../code-review-council/benchmarks/seeded-prs/agentic-login-bypass/head/. .
find . -name '*.py.txt' -exec sh -c 'for path do mv "$path" "${path%.txt}"; done' sh {} +

council review --branch main \
  --output-json council-report.json \
  --output-md council-review.md
```

For stakeholder review, also generate owner HTML:

```bash
council review --branch main \
  --audience owner \
  --output-html owner-report.html
```

## Passing Criteria

A good run should:

- Return `FAIL` or an equivalent blocking verdict for the risky diff.
- Name `src/billing/access.py` with evidence around the untrusted `user_id`
  request parameter.
- Explain the realistic source-to-sink path: request parameter to authorization
  decision.
- Warn about the missing regression test for forged `user_id`.
- Keep `degraded` and `degraded_reasons` visible if any reviewer or Chair output
  loses trust-critical information.

A bad run:

- Silently passes the risky diff.
- Accepts security findings without an exploit path.
- Invents framework, infrastructure, or secret-leak claims outside the fixture.
- Lets owner output hide the accepted technical blocker.

## Roadmap

Future seeded PRs should cover:

- Prompt injection in agent/tool loops.
- GitHub Actions permission and shell-injection mistakes.
- Frontend auth state and accessibility regressions.
- Data migration and PII handling errors.
- Cost-control and timeout/degraded-mode scenarios.

Every new fixture should include expected findings, expected warnings,
non-goals, and documentation explaining how to interpret model variance.

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

## Validate Fixture Metadata

Before using or adding seeded PRs, validate that each fixture has complete
metadata, safe file references, and evidence paths that resolve inside the
fixture:

```bash
council benchmarks validate
```

The command is deterministic and does not call a model. It fails non-zero if
`expected-findings.json` is invalid, a fixture is missing required directories,
an expected file uses path traversal, or a referenced head fixture file is
missing.

## Inspect The Report Shape Without A Model

Generate an illustrative sample report when you want to see the JSON shape that
benchmark scoring expects before setting up model credentials:

```bash
council benchmarks sample-report \
  --fixture benchmarks/seeded-prs/agentic-login-bypass \
  --output council-report.sample.json
```

The sample report is generated from `expected-findings.json`, includes
`benchmark_sample.model_run = false`, and is safe to score:

```bash
council benchmarks score \
  --fixture benchmarks/seeded-prs/agentic-login-bypass \
  --report council-report.sample.json
```

Relative sample-report outputs are written under `--repo`, or the current
directory when `--repo` is omitted. Use an absolute path when you intentionally
want to write elsewhere.

Do not use a sample report as model-quality evidence. It is an onboarding aid
for understanding report fields and score output.

## How To Use A Fixture

Prepare a throwaway git repository from the fixture:

```bash
council benchmarks prepare-run \
  --fixture benchmarks/seeded-prs/agentic-login-bypass \
  --output-dir .council-benchmark-runs/agentic-login-bypass
```

The command materializes inert `.py.txt` files into runnable `.py` files,
commits the safe `base/` tree on `main`, checks out `benchmark-head`, applies
the risky `head/` tree, and prints the review and score commands to run next.
It does not call a model.

Then run Council against the prepared repository:

```bash
council review \
  --repo .council-benchmark-runs/agentic-login-bypass \
  --branch main \
  --output-json .council-benchmark-runs/agentic-login-bypass/council-report.json \
  --output-md .council-benchmark-runs/agentic-login-bypass/council-review.md
```

Score the JSON report against the fixture expectations:

```bash
council benchmarks score \
  --fixture benchmarks/seeded-prs/agentic-login-bypass \
  --report .council-benchmark-runs/agentic-login-bypass/council-report.json
```

For reference, the manual equivalent is: copy `base/`, convert `*.py.txt`
files, commit that safe base, copy `head/`, convert `*.py.txt` files again, then
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

The score command is deterministic and does not call a model. It checks the
report verdict and verifies that expected blockers and warnings are present in
the correct JSON report buckets. Matching always uses file, category, and
severity, and also requires policy ID and line range when the fixture declares
those fields. Score output labels whether the report is an illustrative sample
or an ordinary Council report; the scorer does not prove model provenance for
unmarked reports.

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

# Commercial Readiness Roadmap

Code Review Council should become the trusted, installable review gate for teams
shipping AI-generated pull requests. The commercial promise is not "another AI
review bot"; it is an auditable trust layer with evidence-based findings,
visible degraded mode, deterministic pre-checks, multi-reviewer synthesis, and
merge-safe CI behavior.

## 1. Current Strengths

- Clear product identity: AI reviews AI-generated code through a staged Council
  pipeline instead of a single undifferentiated model call.
- Runtime integrity contract: invalid reviewer output, Chair failures, dropped
  findings, degraded mode, and owner fallback behavior are documented and tested.
- Multi-surface reporting: terminal, JSON, Markdown, HTML, GitHub PR output,
  developer audience, and owner audience exist.
- GitHub Actions rollout path: generated Gemini workflows, BYOK workflow, and a
  version-pinned OpenAI gate for external repositories.
- Deterministic quality harness: protected `main` requires Council plus Python
  3.12, Python 3.13, Ruff, strict MkDocs, and wheel build checks.
- Agent harness: `AGENTS.md`, code review rubric, testing guide, integrity
  policy, security guide, quality guide, PR template, and issue templates all
  push future work toward small evidence-backed changes.
- Release evidence: `v0.3.0` has a tagged release smoke proving install,
  package version, CLI availability, and generated OpenAI gate pinning.

## 2. Current Blockers

- Installability is still source/GitHub-first; PyPI publication, install smoke
  from PyPI, and release notes are not yet part of the public loop.
- The 10-minute first-run path needs a tighter demo story with expected outputs,
  example reports, and a seeded risky PR.
- Benchmark proof is not yet packaged: there is no repeatable seeded-risk suite
  measuring true positives, false positives, degraded handling, cost, or latency.
- Domain packs are still conceptual; prompts, policy templates, test fixtures,
  and pricing boundaries are not separated by domain.
- Reporting is artifact-based; there is no dashboard over JSON/history trends.
- SARIF, audit exports, and enterprise evidence bundles are not available.
- Cost controls exist through model choice and concurrency, but there is no
  productized cost budget, estimate, or policy-by-repo preset.
- GitHub App, Marketplace listing, and hosted reporting boundaries are not
  designed yet.

## 3. Required Launch Checklist

- Publish an installable package from a tagged release and prove `pip install
  code-review-council` exposes `council --version`.
- Keep release contract tests aligned across `pyproject.toml`, `council
  --version`, release smoke, and generated GitHub workflow pins.
- Provide a 10-minute path: install, `council init`, `council doctor`, local
  review, GitHub PR gate, JSON artifact, and owner HTML report.
- Ship at least one demo repository or fixture PR with seeded risks and expected
  Council output.
- Publish benchmark methodology with seeded findings, expected verdicts, and
  known limitations.
- Document cost-control presets for solo, team, and strict CI usage.
- Preserve reporter parity and integrity behavior through tests before adding
  any dashboard, SARIF, GitHub App, or hosted reporting feature.
- Provide security disclosure, secret-handling guidance, and untrusted-input
  boundaries in every enterprise-facing surface.

## 4. Release And Packaging Plan

1. Keep package metadata specific to Council's commercial category: AI code
   review, AI-generated pull requests, GitHub Actions, coding agents, evidence,
   and CI quality gates.
2. Add PyPI publication only after the release smoke can validate the published
   artifact, not just a GitHub tag.
3. Split release checks into source install, wheel install, generated workflow
   pin, and CLI smoke.
4. Add release notes for every tagged version with upgrade, behavior, docs, and
   integrity-impact sections.
5. Add a rollback playbook for bad tags, bad package metadata, or broken
   generated gate pins.

## 5. Adoption Funnel

| Stage | User Goal | Product Evidence |
| --- | --- | --- |
| Discover | Understand why Council exists | README, docs homepage, package metadata, example report |
| Install | Get the CLI working | `pip install`, `council --version`, `council doctor` |
| First review | See value locally | `council review --output-md --output-html` |
| Team gate | Protect PRs | Generated workflow, required checks, JSON artifact |
| Agent loop | Feed accepted findings back | Agent Loop guide and machine-readable JSON |
| Scale | Roll out safely | Adoption guide, release smoke, branch protection checklist |
| Govern | Audit AI-generated changes | History, dashboards, SARIF, audit exports |

## 6. Pricing And Packaging Hypothesis

- Open core: local CLI, core reviewers, GitHub Actions workflows, JSON/Markdown/
  HTML outputs, integrity policy, and basic history remain open.
- Team paid layer: domain packs, policy templates, cost presets, dashboard
  views, benchmark reports, and managed rollout checklists.
- Enterprise layer: GitHub App, hosted reporting, SSO/audit exports, SARIF,
  policy attestations, managed model routing, and compliance/domain packs.
- Services wedge: rollout support for teams adopting AI coding agents at scale,
  including benchmark customization and governance policy design.

## 7. Domain Pack Roadmap

1. AI agent safety pack: prompt injection, tool-call safety, sandbox boundaries,
   generated-code provenance, and agent repair-loop checks.
2. Frontend pack: accessibility, state consistency, hydration/runtime risks,
   user-visible regression evidence, and test selectors.
3. DevOps pack: workflow pins, permissions, shell injection, secrets, runner
   compatibility, deployment gates, and rollback safety.
4. Fintech pack: money movement, audit logging, authorization, data retention,
   rounding, reconciliation, and privacy rules.
5. ServiceNow pack: workflow/business-rule guardrails, ACL risks, integration
   credentials, and change-management evidence.
6. Data pack: schema migration safety, lineage, PII handling, dashboard metric
   correctness, and batch failure visibility.

Each pack needs prompts, policy IDs, seeded benchmark PRs, expected findings,
and reporter examples before it becomes a commercial SKU.

## 8. Enterprise Trust Checklist

- Branch protection requires Council plus deterministic tests, lint, docs, and
  package checks.
- All report formats preserve verdict, degraded reasons, accepted blockers,
  warnings, dismissed findings, reviewer health, and transport notes.
- Owner mode remains a presentation layer and never hides accepted technical
  findings.
- Config, diffs, prompts, model output, reports, PR metadata, and GitHub event
  payloads are treated as untrusted input.
- Secrets are never logged, echoed, embedded in reports, or accepted through
  committed config.
- Release artifacts are reproducible from a tag and tied to release smoke
  evidence.
- Audit exports can prove what was reviewed, what was skipped, what degraded,
  what failed closed, and what humans accepted.

## 9. 30 Day Execution Plan

| Week | Focus | Deliverables |
| --- | --- | --- |
| 1 | Release readiness | PyPI metadata, package publish plan, wheel/PyPI smoke, release notes template |
| 2 | 10-minute onboarding | Demo fixture repo or seeded PR, quickstart report examples, owner HTML sample |
| 3 | Benchmark proof | Seeded risky PR suite, scoring rubric, cost/latency capture, benchmark docs |
| 4 | Commercial packaging | Domain pack architecture, paid-pack boundaries, dashboard/SARIF design notes |

## 10. Metrics To Prove Product Value

- Time to first local review from clean environment.
- Time to first protected GitHub PR gate.
- Install success rate by OS and Python version.
- True positive, false positive, and false negative rates on seeded benchmark PRs.
- Percentage of findings with file/line evidence and policy IDs.
- Degraded-mode rate by provider/model and failure category.
- Reporter parity regressions caught before merge.
- Average review latency and model cost per PR.
- Accepted-blocker fix rate after agent repair loops.
- Number of repos with Council as a required status check.

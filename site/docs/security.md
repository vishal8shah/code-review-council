# Security

## Evidence-based chair policy (plain English)

The chair does not accept severe findings without evidence.

- Hardcoded secrets with concrete evidence are treated as **critical blockers**.
- Injection findings should show an exploitability chain, such as:
  1. untrusted input,
  2. insufficient validation or sanitization,
  3. unsafe sink and plausible payload/path.

## BYOK threat model

When running bring-your-own-key workflows:

- Run only on branches and repositories you control.
- Use restricted API keys with least privilege.
- Assume workflow inputs are untrusted until validated.

## BYOK input validation

The BYOK workflow validates/sanitizes key inputs such as `BASE_REF` and `UPSTREAM_REPO`, and uses git reference checks (`git check-ref-format`) before resolving target refs.

## Merge gates

Council is commonly used as a CI gate and **can block merges when configured**. Local CLI runs remain advisory by default.

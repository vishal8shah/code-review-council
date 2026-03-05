# Contributing

Thanks for improving Code Review Council.

## Setup

```bash
pip install -e .
```

## Run tests

```bash
pytest -q
```

## Add a new reviewer persona

1. Add/update a prompt in `prompts/`.
2. Add reviewer config in `.council.toml`.
3. Ensure reviewer output schema compatibility.
4. Add/adjust tests to cover behavior.

## Open issues and PRs

Please open issues for bugs/feature requests and PRs with clear scope, rationale, and test evidence.

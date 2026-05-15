# Implementation Plan Template

Use this template before complex or risky work in Code Review Council.

Create a plan when the task:

- Touches more than three files.
- Changes reporter behavior.
- Changes integrity policy.
- Changes CLI flags or exit behavior.
- Changes GitHub workflows.
- Changes prompts.
- Changes model transport.
- Changes config schema.
- Changes public docs or README claims.
- Changes merge-gate behavior.

## Goal

Describe the user-facing outcome and why it matters.

## Current State

Summarize the relevant current code, docs, tests, commands, and constraints.
Name the files inspected.

## Target State

Describe the intended behavior after the change. Include any public interfaces,
schemas, CLI flags, report fields, config keys, or docs claims that will change.

## Files Likely Involved

List expected files or modules. Keep this focused and update it if discovery
changes the scope.

## Risks

Call out risks such as:

- Silent PASS behavior.
- Invalid JSON being treated as success.
- Dropped findings hidden from reporters.
- Evidence-free findings being accepted.
- Chair synthesis hiding serious dissent.
- Reporter drift across output surfaces.
- Docs disagreeing with CLI behavior.

## Test Plan

List focused tests and full validation commands. Include reporter, CLI,
integrity, and docs checks when relevant.

## Rollback Plan

Explain how to revert the change safely and what state should remain valid.

## Decision Log

- `<date>`: `<decision>` - `<reason>`

## Done When

- Implementation matches target state.
- Tests cover new or changed behavior.
- Docs are updated when public behavior changes.
- Reporter parity is verified when outputs change.
- Validation commands pass or failures are explicitly explained.

"""CLI entry point for the Code Review Council.

Usage:
    council review              # Advisory mode (local)
    council review --ci         # CI mode (blocks on FAIL)
    council review --staged     # Review staged changes only
    council review --branch main  # Diff against a branch
    council init                # Initialize .council.toml in repo
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(
    name="council",
    help="Code Review Council — Multi-agent LLM code review gate",
    no_args_is_help=True,
)
console = Console()
history_app = typer.Typer(help="Inspect local Council review history.", no_args_is_help=True)
app.add_typer(history_app, name="history")


def _status_style(status: str) -> str:
    if status == "PASS":
        return "green"
    if status == "INFO":
        return "cyan"
    if status == "WARN":
        return "yellow"
    return "red"


def _write_artifact_reports(
    *,
    verdict,
    review_pack,
    reviewer_outputs,
    config,
    ci: bool,
    output_md: str | None,
    output_json: str | None,
    output_html: str | None,
    audience: str,
) -> list[str]:
    """Write file-based reports and return persisted output mode names."""
    output_modes: list[str] = []
    md_path = output_md
    if md_path is None and config.reporters.markdown:
        md_path = ".council-review.md"
    if md_path:
        from .reporters.markdown import write_markdown_report
        write_markdown_report(
            verdict=verdict,
            output_path=md_path,
            review_pack=review_pack,
            reviewer_outputs=reviewer_outputs,
            audience=audience,
        )
        console.print(f"  Review saved to: {md_path}", style="dim")
        output_modes.append("markdown")

    json_path = output_json
    if json_path is None and ci:
        json_path = "council-report.json"
    json_config = config.reporters.json_report
    if json_path is None and json_config is True:
        json_path = "council-report.json"
    if json_path is None and json_config == "ci" and ci:
        json_path = "council-report.json"
    if json_path:
        from .reporters.json_report import write_json_report
        write_json_report(
            verdict=verdict,
            output_path=json_path,
            review_pack=review_pack,
            reviewer_outputs=reviewer_outputs,
        )
        console.print(f"  JSON report saved to: {json_path}", style="dim")
        output_modes.append("json")

    if output_html:
        from .reporters.html_report import write_html_report
        write_html_report(
            verdict=verdict,
            output_path=output_html,
            audience=audience,
            review_pack=review_pack,
            reviewer_outputs=reviewer_outputs,
        )
        console.print(f"  HTML report saved to: {output_html}", style="dim")
        output_modes.append("html")

    return output_modes


def _post_github_pr_report(*, verdict, reviewer_outputs, enabled: bool) -> str | None:
    """Post the GitHub PR report when enabled and return its output mode."""
    if not enabled:
        return None

    from .reporters.github_pr import post_github_pr_review
    posted = post_github_pr_review(verdict, reviewer_outputs=reviewer_outputs)
    if not posted:
        console.print("  [dim]GitHub PR comment not posted (missing env/PR context or API failure).[/]")
    return "github_pr"


def _record_history_best_effort(
    *,
    root: Path,
    config,
    result,
    ci: bool,
    staged: bool,
    branch: str | None,
    audience: str,
    output_modes: list[str],
    started: float,
) -> None:
    """Persist review history without changing review exit behavior."""
    if not config.history.enabled:
        return

    try:
        from .history import record_review_history

        history_path = record_review_history(
            repo_root=root,
            config=config,
            verdict=result.verdict,
            review_pack=result.review_pack,
            reviewer_outputs=result.reviewer_outputs,
            gate_result=result.gate_result,
            ci_mode=ci,
            staged=staged,
            branch=branch,
            audience=audience,
            output_modes=output_modes,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        console.print(f"  History recorded to: {history_path}", style="dim")
    except Exception as exc:
        console.print(f"  [dim]History not recorded: {exc}[/]")


def _enforce_ci_exit_code(*, ci: bool, verdict, config) -> None:
    """Apply existing CI/advisory exit semantics."""
    if ci and verdict.degraded and config.enforcement.on_integrity_issue == "fail":
        console.print(
            "\n  Merge blocked: integrity issues detected in degraded review run "
            "(on_integrity_issue=fail).",
            style="bold red",
        )
        raise typer.Exit(code=1)

    if ci and verdict.verdict == "FAIL":
        console.print("\n  Merge blocked. Fix issues and push again.", style="bold red")
        raise typer.Exit(code=1)
    if ci and verdict.verdict == "PASS_WITH_WARNINGS":
        block_on = config.enforcement.ci_block_on
        if block_on == "PASS_WITH_WARNINGS":
            console.print("\n  Merge blocked (ci_block_on=PASS_WITH_WARNINGS).", style="bold red")
            raise typer.Exit(code=1)

    if not ci and verdict.verdict == "FAIL":
        console.print("  [INFO] These findings will be enforced in CI.", style="yellow")


@app.command()
def review(
    ci: bool = typer.Option(False, "--ci", help="CI mode: exit 1 on FAIL, force JSON output"),
    staged: bool = typer.Option(False, "--staged", help="Review staged changes only"),
    branch: str = typer.Option(None, "--branch", "-b", help="Diff against this branch"),
    output_json: str = typer.Option(None, "--output-json", help="Write JSON report to this path"),
    output_md: str = typer.Option(None, "--output-md", help="Write markdown report to this path (respects --audience)"),
    output_html: str = typer.Option(None, "--output-html", help="Write HTML report to this path"),
    github_pr: bool = typer.Option(False, "--github-pr", help="Post/update a sticky GitHub PR comment and emit workflow annotations"),
    audience: str = typer.Option(
        None,
        "--audience",
        help="Output audience: 'developer' (default, technical) or 'owner' (plain-English for product owners)",
    ),
    repo_root: str = typer.Option(None, "--repo", help="Path to git repository root"),
) -> None:
    """Run the Code Review Council on current changes."""
    from .config import load_config
    from .orchestrator import run_council

    root = Path(repo_root) if repo_root else Path.cwd()
    config = load_config(root)
    started = time.monotonic()

    # Resolve audience: CLI flag > config default > "developer"
    resolved_audience = audience or config.presentation.default_audience or "developer"
    if resolved_audience not in ("developer", "owner"):
        console.print(
            f"[red]Invalid --audience value '{resolved_audience}'. "
            "Must be 'developer' or 'owner'.[/]"
        )
        raise typer.Exit(code=1)

    # Safety: warn if --ci without explicit diff target (could review empty diff)
    if ci and not staged and not branch:
        console.print(
            "  [yellow][WARN] --ci mode without --branch or --staged. "
            "This may produce an empty diff in CI checkouts. "
            "Use --branch main (or your base branch) for PR reviews.[/]"
        )

    # Run the async pipeline
    result = asyncio.run(
        run_council(
            repo_root=root,
            config=config,
            staged=staged,
            branch=branch,
        )
    )

    verdict = result.verdict

    # Owner presentation — generated after synthesis, only when requested
    if resolved_audience == "owner":
        from .chair import generate_owner_presentation
        verdict.owner_presentation = asyncio.run(
            generate_owner_presentation(
                verdict=verdict,
                chair_model=config.chair_model,
                timeout=float(config.timeout_seconds),
            )
        )

    # Stage 3: Reports
    # Terminal output (always)
    from .reporters.terminal import print_verdict
    print_verdict(
        verdict=verdict,
        review_pack=result.review_pack,
        reviewer_outputs=result.reviewer_outputs,
        gate_result=result.gate_result,
        ci_mode=ci,
        audience=resolved_audience,
    )
    output_modes = _write_artifact_reports(
        verdict=verdict,
        review_pack=result.review_pack,
        reviewer_outputs=result.reviewer_outputs,
        config=config,
        ci=ci,
        output_md=output_md,
        output_json=output_json,
        output_html=output_html,
        audience=resolved_audience,
    )
    pr_mode = _post_github_pr_report(
        verdict=verdict,
        reviewer_outputs=result.reviewer_outputs,
        enabled=github_pr or config.reporters.github_pr,
    )
    if pr_mode is not None:
        output_modes.append(pr_mode)

    _record_history_best_effort(
        root=root,
        config=config,
        result=result,
        ci=ci,
        staged=staged,
        branch=branch,
        audience=resolved_audience,
        output_modes=output_modes,
        started=started,
    )
    _enforce_ci_exit_code(ci=ci, verdict=verdict, config=config)


@app.command()
def doctor(
    branch: str = typer.Option(None, "--branch", "-b", help="Validate this diff target branch/ref"),
    audience: str = typer.Option(
        None,
        "--audience",
        help="Validate this audience override (`developer` or `owner`) instead of the config default.",
    ),
    github_pr: bool = typer.Option(
        False,
        "--github-pr",
        help="Also validate GitHub pull-request reporting environment variables.",
    ),
    repo_root: str = typer.Option(None, "--repo", help="Path to git repository root"),
) -> None:
    """Run practical preflight checks before a full council review."""
    from pathlib import Path

    from .config import load_config
    from .doctor import build_doctor_next_steps, build_review_profile, run_doctor

    root = Path(repo_root) if repo_root else Path.cwd()
    config = load_config(root)
    report = run_doctor(
        repo_root=root,
        config=config,
        branch=branch,
        audience=audience,
        github_pr=github_pr,
    )

    console.print("\n[bold]Code Review Council Doctor[/]")
    for check in report.checks:
        style = _status_style(check.status)
        console.print(f"  [{style}]{check.status:4}[/] {check.name}: {check.detail}")
        if check.remediation:
            console.print(f"        -> {check.remediation}", style="dim")

    console.print("\n  [bold]Review profile[/]")
    for line in build_review_profile(config):
        console.print(f"    - {line}", style="dim")

    console.print("\n  [bold]Recommended next steps[/]")
    for step in build_doctor_next_steps(report, branch=branch, github_pr=github_pr):
        console.print(f"    - {step}", style="dim")

    if report.exit_code != 0:
        console.print("\n  Doctor found blocking setup issues.", style="bold red")
        raise typer.Exit(code=1)

    console.print("\n  Doctor completed with no blocking issues.", style="bold green")


@history_app.command("summary")
def history_summary(
    days: int = typer.Option(30, "--days", help="Number of recent days to summarize."),
    limit: int = typer.Option(10, "--limit", help="Maximum repeated fingerprints to show."),
    repo_root: str = typer.Option(None, "--repo", help="Path to git repository root"),
) -> None:
    """Print local repeated-finding and debt trends for this repository."""
    from .config import load_config
    from .history import (
        HistoryPathError,
        HistorySchemaError,
        format_history_summary,
        summarize_history,
    )

    root = Path(repo_root) if repo_root else Path.cwd()
    config = load_config(root)
    if not config.history.enabled:
        console.print("History is disabled for this repository.", style="dim")
        return

    try:
        summary = summarize_history(
            repo_root=root,
            history_config=config.history,
            days=max(1, days),
            limit=max(1, limit),
        )
    except (OSError, sqlite3.Error, HistoryPathError, HistorySchemaError) as exc:
        console.print(f"History summary failed: {exc}", style="red")
        raise typer.Exit(code=1) from exc

    for line in format_history_summary(summary):
        console.print(line)


@app.command()
def init(
    repo_root: str = typer.Option(None, "--repo", help="Path to git repository root"),
) -> None:
    """Initialize .council.toml and default prompts in your repository."""
    root = Path(repo_root) if repo_root else Path.cwd()

    config_path = root / ".council.toml"
    if config_path.exists():
        console.print(f"[yellow].council.toml already exists at {config_path}[/]")
        overwrite = typer.confirm("Overwrite?", default=False)
        if not overwrite:
            raise typer.Exit()

    config_path.write_text(_DEFAULT_CONFIG, encoding="utf-8")
    console.print(f"  [green]Created[/] {config_path}")

    # Create .councilignore
    ignore_path = root / ".councilignore"
    if not ignore_path.exists():
        ignore_path.write_text(_DEFAULT_COUNCILIGNORE, encoding="utf-8")
        console.print(f"  [green]Created[/] {ignore_path}")

    # Create default prompt files
    prompts_dir = root / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, content in _DEFAULT_PROMPTS.items():
        prompt_path = root / rel_path
        if not prompt_path.exists():
            prompt_path.write_text(content, encoding="utf-8")
            console.print(f"  [green]Created[/] {prompt_path}")

    # Create GitHub Actions workflow
    workflow_dir = root / ".github" / "workflows"
    workflow_path = workflow_dir / "council-review.yml"
    byok_workflow_path = workflow_dir / "council-byok.yml"
    openai_gate_path = workflow_dir / "council-openai-gate.yml"
    if not workflow_path.exists() or not byok_workflow_path.exists() or not openai_gate_path.exists():
        workflow_dir.mkdir(parents=True, exist_ok=True)

    if not workflow_path.exists():
        workflow_path.write_text(_DEFAULT_WORKFLOW, encoding="utf-8")
        console.print(f"  [green]Created[/] {workflow_path}")
        console.print(
            "  [dim]→ Add GOOGLE_API_KEY to your repo secrets for the Gemini-pinned workflow[/]"
        )

    if not byok_workflow_path.exists():
        byok_workflow_path.write_text(_DEFAULT_WORKFLOW_BYOK, encoding="utf-8")
        console.print(f"  [green]Created[/] {byok_workflow_path}")

    if not openai_gate_path.exists():
        openai_gate_path.write_text(_DEFAULT_WORKFLOW_OPENAI_GATE, encoding="utf-8")
        console.print(f"  [green]Created[/] {openai_gate_path}")
        console.print(
            "  [dim]→ Add OPENAI_API_KEY to required-gate repos that use council-openai-gate.yml[/]"
        )

    console.print("\n  Council initialized.", style="bold green")
    console.print("  [bold]Recommended next steps[/]")
    console.print(
        "    - Add GOOGLE_API_KEY to GitHub Actions secrets for the generated Gemini workflows.",
        style="dim",
    )
    console.print(
        "    - For TS/JS required gates across other repos, use council-openai-gate.yml with OPENAI_API_KEY.",
        style="dim",
    )
    console.print(
        "    - Run `council doctor --branch main` to validate keys, models, and the diff target.",
        style="dim",
    )
    console.print("    - Run `council review --branch main` for your first local advisory review.", style="dim")
    console.print("    - Run `council history summary --days 30` after a few reviews to spot repeat debt.", style="dim")


_DEFAULT_CONFIG = """\
[council]
chair_model = "openai/gpt-4o"
chair_reasoning_effort = ""
fail_on = "FAIL"
timeout_seconds = 60
reviewer_timeout_seconds = 60
reviewer_concurrency = 2

[council.enforcement]
mode = "ci"
ci_block_on = "FAIL"
local_mode = "advisory"
on_integrity_issue = "fail"

[preprocessor]
max_review_tokens = 20000
max_file_tokens = 8000
ignore_file = ".councilignore"
detect_generated = true

[gate_zero]
require_docs = true
require_type_annotations = true
require_readme_on_new_module = true
check_secrets = true
max_file_lines = 1000

[gate_zero.linters]
python = "ruff check --diff"

[gate_zero.analyzers]
python = true
typescript = true  # parser-free TS heuristics; set false to opt out
javascript = true  # parser-free JS heuristics; set false to opt out

[[reviewers]]
id = "secops"
name = "Security Operations Reviewer"
model = "openai/gpt-5.2"
prompt = "prompts/secops.md"
enabled = true

[[reviewers]]
id = "qa"
name = "QA Engineer"
model = "openai/gpt-5.2"
prompt = "prompts/qa.md"
enabled = true

[[reviewers]]
id = "architect"
name = "Solutions Architect"
model = "openai/gpt-4o"
prompt = "prompts/architecture.md"
enabled = true

[[reviewers]]
id = "docs"
name = "Documentation Reviewer"
model = "openai/gpt-4o-mini"
prompt = "prompts/docs.md"
enabled = true

[reporters]
terminal = true
markdown = true
json_report = "ci"
github_pr = false

[context]
full_repo_tests = true
max_test_files = 500
max_test_file_bytes = 20000

[history]
enabled = true
path = ""
retention_days = 180
store_finding_text = false

[cost]
warn_threshold_usd = 1.00
budget_daily_usd = 20.00
"""

_DEFAULT_COUNCILIGNORE = """\
# Files to exclude from LLM review (gitignore syntax)
package-lock.json
yarn.lock
pnpm-lock.yaml
Pipfile.lock
poetry.lock
*.min.js
*.min.css
*.map
*.generated.*
vendor/
dist/
build/
node_modules/
__pycache__/
*.egg-info/
"""

_DEFAULT_WORKFLOW = """\
name: Code Review Council
on: [pull_request]

jobs:
  council-review:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      issues: write
      contents: read
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11
        with:
          fetch-depth: 0

      - uses: actions/setup-python@82c7e631bb3cdc910f68e0081d67478d79c6982d
        with:
          python-version: '3.12'

      - name: Install Code Review Council
        run: pip install .

      - name: Check Gemini credentials availability
        id: llm_keys
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
        run: |
          if [ -n "$GOOGLE_API_KEY" ]; then
            echo "has_key=true" >> "$GITHUB_OUTPUT"
          else
            echo "has_key=false" >> "$GITHUB_OUTPUT"
            echo "::notice title=Code Review Council skipped::No GOOGLE_API_KEY available. This workflow is pinned to Gemini and will skip instead of falling back to other providers."
            printf '{"skipped":"no_google_api_key","how_to_fix":"Add GOOGLE_API_KEY as a repository Actions secret, then rerun this workflow."}\n' > council-report.json
          fi

      - name: Write CI Gemini config
        if: steps.llm_keys.outputs.has_key == 'true'
        run: |
          cat > .council.toml <<'EOF'
          [council]
          chair_model = "gemini/gemini-3-pro-preview"
          timeout_seconds = 360
          reviewer_timeout_seconds = 360
          reviewer_concurrency = 1

          [[reviewers]]
          id = "secops"
          name = "Security Operations Reviewer"
          model = "gemini/gemini-3-pro-preview"
          prompt = "prompts/secops.md"
          enabled = true

          [[reviewers]]
          id = "qa"
          name = "QA Engineer"
          model = "gemini/gemini-3-pro-preview"
          prompt = "prompts/qa.md"
          enabled = true

          [[reviewers]]
          id = "architect"
          name = "Solutions Architect"
          model = "gemini/gemini-3-pro-preview"
          prompt = "prompts/architecture.md"
          enabled = true

          [[reviewers]]
          id = "docs"
          name = "Documentation Reviewer"
          model = "gemini/gemini-3-pro-preview"
          prompt = "prompts/docs.md"
          enabled = true
          EOF

      - name: Run Council Review
        if: steps.llm_keys.outputs.has_key == 'true'
        run: council review --ci --github-pr --branch "$BASE_REF" --output-json council-report.json
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          BASE_REF: ${{ github.base_ref }}

      - name: Upload Review Report
        uses: actions/upload-artifact@65462800fd760344b1a7b4382951275a0abb4808
        if: always()
        with:
          name: council-report
          path: council-report.json
"""

_DEFAULT_WORKFLOW_BYOK = """\
name: Code Review Council (BYOK - Fork)
on:
  workflow_dispatch:
    inputs:
      base_ref:
        description: Diff target branch/ref (usually main)
        required: false
        default: main
      upstream_repo:
        description: Optional upstream repository in owner/name format for accurate PR-base diffs
        required: false
        default: ""
      audience:
        description: Report audience passed to --audience (developer or owner)
        required: false
        default: developer

jobs:
  council-review-byok:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11
        with:
          fetch-depth: 0

      - uses: actions/setup-python@82c7e631bb3cdc910f68e0081d67478d79c6982d
        with:
          python-version: '3.12'

      - name: Install Code Review Council
        run: pip install .

      - name: Fail fast if no Gemini key configured
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
        run: |
          if [ -z "$GOOGLE_API_KEY" ]; then
            printf '{"skipped":"no_google_api_key","how_to_fix":"Add GOOGLE_API_KEY as an Actions secret in your fork, then rerun."}\n' > council-report.json
            printf '# Council BYOK skipped\n\nNo GOOGLE_API_KEY secret found. This workflow is pinned to Gemini. Add GOOGLE_API_KEY in your fork and rerun.\n' > council-review.md
            echo "::error::No GOOGLE_API_KEY found. This workflow is pinned to Gemini. Add GOOGLE_API_KEY as an Actions secret in your fork repository, then rerun this workflow."
            exit 1
          fi

      - name: Resolve review base ref
        id: review_base
        env:
          UPSTREAM_REPO: ${{ inputs.upstream_repo }}
          BASE_REF: ${{ inputs.base_ref }}
        run: |
          set -euo pipefail

          fail() {
            case "$1" in
              invalid_base_ref)
                printf '{"skipped":"invalid_base_ref","how_to_fix":"Use a valid base_ref (for example: main or release/1.2)."}
' > council-report.json
                printf '# Council BYOK skipped

Invalid base_ref input. Use a valid git branch/ref format and rerun.
' > council-review.md
                ;;
              invalid_upstream_repo)
                printf '{"skipped":"invalid_upstream_repo","how_to_fix":"Set upstream_repo to owner/repo format (for example: org/project) and rerun."}
' > council-report.json
                printf '# Council BYOK skipped

Invalid upstream_repo input. Use owner/repo format and rerun.
' > council-review.md
                ;;
              upstream_fetch_failed)
                printf '{"skipped":"upstream_fetch_failed","how_to_fix":"Verify upstream_repo is correct and base_ref exists (and repo is public or accessible), then rerun."}
' > council-report.json
                printf '# Council BYOK skipped

Failed to fetch upstream base ref. Check upstream_repo/base_ref and rerun.
' > council-review.md
                ;;
              *)
                printf '{"skipped":"invalid_base_ref","how_to_fix":"Use a valid base_ref (for example: main or release/1.2)."}
' > council-report.json
                printf '# Council BYOK skipped

Invalid input.
' > council-review.md
                ;;
            esac
            echo "::error::$2"
            exit 1
          }

          if [ -z "$BASE_REF" ]; then
            fail invalid_base_ref "Invalid base_ref."
          fi
          if [[ "$BASE_REF" == -* ]]; then
            fail invalid_base_ref "Invalid base_ref."
          fi
          if [[ "$BASE_REF" == /* ]]; then
            fail invalid_base_ref "Invalid base_ref."
          fi
          if [[ "$BASE_REF" == *..* ]]; then
            fail invalid_base_ref "Invalid base_ref."
          fi
          if [[ ! "$BASE_REF" =~ ^[A-Za-z0-9_][A-Za-z0-9_./-]*$ ]]; then
            fail invalid_base_ref "Invalid base_ref."
          fi
          if [[ "$BASE_REF" == refs/* ]]; then
            git check-ref-format "$BASE_REF" >/dev/null 2>&1 || fail invalid_base_ref "Invalid base_ref."
          else
            git check-ref-format --branch "$BASE_REF" >/dev/null 2>&1 || fail invalid_base_ref "Invalid base_ref."
          fi

          if [ -n "$UPSTREAM_REPO" ]; then
            if [[ ! "$UPSTREAM_REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
              fail invalid_upstream_repo "Invalid upstream_repo format. Expected owner/repo."
            fi
            UPSTREAM_URL="https://github.com/${UPSTREAM_REPO}.git"
            if git remote get-url upstream >/dev/null 2>&1; then
              git remote set-url upstream "$UPSTREAM_URL"
            else
              git remote add upstream "$UPSTREAM_URL"
            fi
            if ! git fetch --no-tags upstream -- "$BASE_REF"; then
              fail upstream_fetch_failed "Failed to fetch upstream base ref."
            fi
            TARGET="upstream/${BASE_REF}"
          else
            TARGET="$BASE_REF"
          fi

          echo "target=${TARGET}" >> "$GITHUB_OUTPUT"
      - name: Warn if workflow is running on the base branch
        env:
          BASE_REF: ${{ inputs.base_ref }}
        run: |
          echo "Running on ref: $GITHUB_REF_NAME"
          if [ "$GITHUB_REF_NAME" = "$BASE_REF" ]; then
            echo "::warning::You are running on the base branch '$BASE_REF'. You probably meant to run this workflow on your PR branch."
          fi

      - name: Write CI Gemini config
        run: |
          cat > .council.toml <<'EOF'
          [council]
          chair_model = "gemini/gemini-3-pro-preview"
          timeout_seconds = 360
          reviewer_timeout_seconds = 360
          reviewer_concurrency = 1

          [[reviewers]]
          id = "secops"
          name = "Security Operations Reviewer"
          model = "gemini/gemini-3-pro-preview"
          prompt = "prompts/secops.md"
          enabled = true

          [[reviewers]]
          id = "qa"
          name = "QA Engineer"
          model = "gemini/gemini-3-pro-preview"
          prompt = "prompts/qa.md"
          enabled = true

          [[reviewers]]
          id = "architect"
          name = "Solutions Architect"
          model = "gemini/gemini-3-pro-preview"
          prompt = "prompts/architecture.md"
          enabled = true

          [[reviewers]]
          id = "docs"
          name = "Documentation Reviewer"
          model = "gemini/gemini-3-pro-preview"
          prompt = "prompts/docs.md"
          enabled = true
          EOF

      - name: Run Council Review (BYOK)
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
          TARGET_BRANCH: ${{ steps.review_base.outputs.target }}
          AUDIENCE: ${{ inputs.audience }}
        run: |
          if [ "$AUDIENCE" != "developer" ] && [ "$AUDIENCE" != "owner" ]; then
            printf '{"skipped":"invalid_audience","how_to_fix":"Set audience to developer or owner and rerun"}\n' > council-report.json
            printf '# Council BYOK skipped\n\nInvalid audience input. Use developer or owner and rerun.\n' > council-review.md
            echo "::error::Invalid audience. Expected developer or owner."
            exit 1
          fi

          council review --ci --branch "$TARGET_BRANCH" --audience "$AUDIENCE" --output-json council-report.json --output-md council-review.md

      - name: Upload Review Report
        uses: actions/upload-artifact@65462800fd760344b1a7b4382951275a0abb4808
        if: always()
        with:
          name: council-report
          path: |
            council-report.json
            council-review.md
"""


_DEFAULT_WORKFLOW_OPENAI_GATE = """\
name: Code Review Council OpenAI Gate
on: [pull_request]

env:
  COUNCIL_INSTALL_SPEC: git+https://github.com/vishal8shah/code-review-council.git@main

jobs:
  council-review:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      issues: write
      contents: read
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11
        with:
          fetch-depth: 0

      - uses: actions/setup-python@82c7e631bb3cdc910f68e0081d67478d79c6982d
        with:
          python-version: '3.12'

      - name: Install Code Review Council
        run: pip install "$COUNCIL_INSTALL_SPEC"

      - name: Fail fast if OpenAI key is unavailable
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          if [ -z "$OPENAI_API_KEY" ]; then
            printf '{"skipped":"no_openai_api_key","how_to_fix":"Add OPENAI_API_KEY as a repository Actions secret, then rerun this workflow."}\n' > council-report.json
            echo "::error::No OPENAI_API_KEY available. This required gate is pinned to OpenAI and fails closed when the key is missing."
            exit 1
          fi

      - name: Write CI OpenAI config
        run: |
          cat > .council.toml <<'EOF'
          [council]
          chair_model = "openai/gpt-5.5"
          chair_reasoning_effort = "medium"
          timeout_seconds = 360
          reviewer_timeout_seconds = 240
          reviewer_concurrency = 2

          [council.enforcement]
          mode = "ci"
          ci_block_on = "FAIL"
          local_mode = "advisory"
          on_integrity_issue = "fail"

          [gate_zero.analyzers]
          python = true
          typescript = true
          javascript = true

          [[reviewers]]
          id = "secops"
          name = "Security Operations Reviewer"
          model = "openai/gpt-5.2"
          enabled = true

          [[reviewers]]
          id = "qa"
          name = "QA Engineer"
          model = "openai/gpt-5.2"
          enabled = true

          [[reviewers]]
          id = "architect"
          name = "Solutions Architect"
          model = "openai/gpt-5.2"
          enabled = true

          [[reviewers]]
          id = "docs"
          name = "Documentation Reviewer"
          model = "openai/gpt-5.2"
          enabled = true
          EOF

      - name: Run Council Review
        run: council review --ci --github-pr --branch "$BASE_REF" --output-json council-report.json
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          BASE_REF: ${{ github.base_ref }}

      - name: Upload Review Report
        uses: actions/upload-artifact@65462800fd760344b1a7b4382951275a0abb4808
        if: always()
        with:
          name: council-report
          path: council-report.json
"""


_DEFAULT_PROMPTS = {
    "prompts/secops.md": """You are a Security Operations code reviewer on a Code Review Council.
Your job is to find security vulnerabilities in code changes.

## Focus Areas
1. Injection vulnerabilities: SQL injection, XSS, command injection, path traversal
2. Authentication & authorization flaws: Missing auth checks, broken access control
3. Secrets & credentials: Hardcoded API keys, tokens, passwords in code
4. Input validation: Missing or insufficient validation of user input
5. Dependency risks: Known vulnerable patterns, unsafe deserialization
6. Cryptographic issues: Weak algorithms, improper key management
7. Error handling that leaks info: Stack traces, internal paths exposed to users

## Severity Guide
- CRITICAL: Exploitable vulnerability (SQL injection, auth bypass, secret exposure)
- HIGH: Security weakness that could lead to exploitation
- MEDIUM: Defense-in-depth issue (missing rate limiting, overly broad CORS)
- LOW: Security hygiene (logging improvements, header hardening)

## Shell & Workflow Injection: Mandatory Evidence Chain
For any injection finding rated HIGH/CRITICAL, you MUST satisfy ALL THREE:
1) Missing/insufficient validation: explicitly show upstream validation is absent or insufficient for the sink.
   - Credit combined validation chains (explicit dangerous-sequence guards + sufficient allowlist + git check-ref-format).
   - If the variable passes a sufficient chain AND is used safely, do NOT flag downstream usage.
2) Unsafe sink: show unquoted use / eval / missing `--` in git commands. Credit double-quoting "$VAR" and `--` as mitigations.
3) Realistic payload: provide an example string that passes existing validation AND changes execution. If you cannot, do NOT rate HIGH/CRITICAL.

- String assignment is not execution (e.g., TARGET="upstream/${VAR}") and must not be flagged as injection.

## Rules
- Only flag issues you have HIGH confidence about
- Every finding MUST cite specific code via evidence_ref
- Do NOT flag theoretical issues without concrete evidence in the diff
- If the code looks secure, return verdict: PASS with empty findings

Respond with ONLY valid JSON matching the requested schema.""",
    "prompts/qa.md": """You are a QA Engineer code reviewer on a Code Review Council.
Your job is to evaluate test coverage, error handling, and edge cases.

## Focus Areas
1. Test coverage gaps: New functions/classes without corresponding tests
2. Error handling: Missing try/except, unhandled edge cases, bare except clauses
3. Edge cases: Boundary conditions, empty inputs, null handling, race conditions
4. Assertion quality: Tests that assert meaningful behavior, not just "no crash"
5. Test isolation: Tests that depend on external state or ordering

## Using the ReviewPack
- Check changed_symbols — any symbol with has_tests=false is a coverage gap
- Check test_coverage_map — source files with empty test lists need attention
- Reference specific symbols and line ranges in your findings

## Severity Guide
- CRITICAL: Code that will crash on common inputs with no error handling
- HIGH: Public function with no tests and no error handling for likely failure modes
- MEDIUM: Missing edge case tests, incomplete error handling
- LOW: Test style issues, minor assertion improvements

## Exception Handling Rules
- Do not rate HIGH just because a try/except catches only SyntaxError if the code already degrades safely (e.g., sets tree=None and continues).
- To rate HIGH, you must (a) name a concrete realistic exception actually raised by that operation in practice, and (b) show the current fallback is unsafe.
- Do not recommend `except Exception` unless you can name at least two specific exceptions that the operation actually raises and the current fallback fails to handle.

## Rules
- Reference the test_coverage_map and changed_symbols data in your evidence
- Every finding must cite specific code
- If test coverage looks adequate, return PASS

Respond with ONLY valid JSON matching the requested schema.""",
    "prompts/architecture.md": """You are a Solutions Architect code reviewer on a Code Review Council.
Your job is to evaluate code structure, design patterns, and maintainability.

## Focus Areas
1. SOLID violations: Single responsibility, interface segregation, dependency inversion
2. Coupling: Tight coupling between modules, circular dependencies
3. Complexity: Functions with high cyclomatic complexity (>10), deep nesting
4. API design: Inconsistent interfaces, leaky abstractions
5. Tech debt indicators: God classes, copy-paste code, magic numbers
6. Decomposition: Large files that should be split (>500 lines of logic)

## Severity Guide
- CRITICAL: Circular dependency or architectural pattern that blocks future changes
- HIGH: SOLID violation in public API, function complexity >15
- MEDIUM: Moderate complexity (10-15), minor coupling issues
- LOW: Style preferences, naming conventions

## Rules
- Focus on structural issues, not style preferences
- Every finding must reference specific symbols and line ranges
- Architecture concerns are MEDIUM unless they create real dependency problems
- If the architecture is clean, return PASS

Respond with ONLY valid JSON matching the requested schema.""",
    "prompts/docs.md": """You are a Documentation reviewer on a Code Review Council.
Gate Zero already checked that docstrings exist. Your job is to evaluate QUALITY.

## Focus Areas
1. Docstring quality: Does it describe what the function does, params, return values?
2. Misleading docs: Documentation that describes wrong behavior is worse than none
3. Inline comments: Are complex algorithms or non-obvious logic explained?
4. API documentation: New endpoints or public interfaces documented with examples?
5. README accuracy: If README was modified, does it reflect the code changes?

## Severity Guide
- CRITICAL: Docstring describes wrong behavior (actively misleading)
- HIGH: Public API function with no meaningful documentation
- MEDIUM: Docstring exists but is incomplete (missing params, return type)
- LOW: Minor formatting issues, typos

## Rules
- Gate Zero already enforces presence. You evaluate quality.
- Only flag genuinely poor or misleading documentation
- Brief but accurate docs are fine — don't demand essays
- If docs are adequate, return PASS

Respond with ONLY valid JSON matching the requested schema.""",
}

def main() -> None:
    """Entry point."""
    app()


if __name__ == "__main__":
    main()

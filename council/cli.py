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
import sys
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(
    name="council",
    help="🏛️ Code Review Council — Multi-agent LLM code review gate",
    no_args_is_help=True,
)
console = Console()


@app.command()
def review(
    ci: bool = typer.Option(False, "--ci", help="CI mode: exit 1 on FAIL, force JSON output"),
    staged: bool = typer.Option(False, "--staged", help="Review staged changes only"),
    branch: str = typer.Option(None, "--branch", "-b", help="Diff against this branch"),
    output_json: str = typer.Option(None, "--output-json", help="Write JSON report to this path"),
    output_md: str = typer.Option(None, "--output-md", help="Write markdown report to this path (respects --audience)"),
    output_html: str = typer.Option(None, "--output-html", help="Write HTML report to this path"),
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
            "  [yellow]⚠ Warning: --ci mode without --branch or --staged. "
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

    # Markdown report
    md_path = output_md
    if md_path is None and config.reporters.markdown:
        md_path = ".council-review.md"
    if md_path:
        from .reporters.markdown import write_markdown_report
        write_markdown_report(
            verdict=verdict,
            output_path=md_path,
            review_pack=result.review_pack,
            reviewer_outputs=result.reviewer_outputs,
            audience=resolved_audience,
        )
        console.print(f"  Review saved to: {md_path}", style="dim")

    # JSON report (always in CI mode, or if explicitly requested)
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
            review_pack=result.review_pack,
            reviewer_outputs=result.reviewer_outputs,
        )
        console.print(f"  JSON report saved to: {json_path}", style="dim")

    # HTML report
    if output_html:
        from .reporters.html_report import write_html_report
        write_html_report(
            verdict=verdict,
            output_path=output_html,
            audience=resolved_audience,
            review_pack=result.review_pack,
            reviewer_outputs=result.reviewer_outputs,
        )
        console.print(f"  HTML report saved to: {output_html}", style="dim")

    # Exit code
    if ci and verdict.verdict == "FAIL":
        console.print("\n  Merge blocked. Fix issues and push again.", style="bold red")
        raise typer.Exit(code=1)
    elif ci and verdict.verdict == "PASS_WITH_WARNINGS":
        block_on = config.enforcement.ci_block_on
        if block_on == "PASS_WITH_WARNINGS":
            console.print("\n  Merge blocked (ci_block_on=PASS_WITH_WARNINGS).", style="bold red")
            raise typer.Exit(code=1)

    # Advisory mode — always exit 0
    if not ci:
        if verdict.verdict == "FAIL":
            console.print("  💡 These findings will be enforced in CI.", style="yellow")


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

    # Create GitHub Actions workflow
    workflow_dir = root / ".github" / "workflows"
    workflow_path = workflow_dir / "council-review.yml"
    if not workflow_path.exists():
        workflow_dir.mkdir(parents=True, exist_ok=True)
        workflow_path.write_text(_DEFAULT_WORKFLOW, encoding="utf-8")
        console.print(f"  [green]Created[/] {workflow_path}")
        console.print(
            "  [dim]→ Add ANTHROPIC_API_KEY and OPENAI_API_KEY to your repo secrets[/]"
        )

    console.print("\n  🏛️ Council initialized. Run [bold]council review[/] to review changes.")


_DEFAULT_CONFIG = """\
[council]
chair_model = "openai/gpt-4o"
fail_on = "FAIL"
timeout_seconds = 60

[council.enforcement]
mode = "ci"
ci_block_on = "FAIL"
local_mode = "advisory"

[preprocessor]
max_review_tokens = 30000
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
typescript = false  # not yet implemented — enable when analyzer is added
javascript = false  # not yet implemented — enable when analyzer is added

[[reviewers]]
id = "secops"
name = "Security Operations Reviewer"
model = "anthropic/claude-sonnet-4-20250514"
enabled = true

[[reviewers]]
id = "qa"
name = "QA Engineer"
model = "anthropic/claude-sonnet-4-20250514"
enabled = true

[[reviewers]]
id = "architect"
name = "Solutions Architect"
model = "anthropic/claude-sonnet-4-20250514"
enabled = true

[[reviewers]]
id = "docs"
name = "Documentation Reviewer"
model = "anthropic/claude-sonnet-4-20250514"
enabled = true

[reporters]
terminal = true
markdown = true
json_report = "ci"
github_pr = false  # not yet implemented — enable when reporter is added

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
      contents: read
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install Code Review Council
        run: pip install .

      - name: Run Council Review
        run: council review --ci --branch ${{ github.base_ref }} --output-json council-report.json
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}

      - name: Upload Review Report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: council-report
          path: council-report.json
"""


def main() -> None:
    """Entry point."""
    app()


if __name__ == "__main__":
    main()

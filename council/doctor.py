"""Preflight diagnostics for practical Council setup issues."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import CouncilConfig, load_config
from .llm_transport import classify_model_json_support, provider_env_var_for_model

_GIT_TIMEOUT_SECONDS = 10.0
_MAX_EVENT_FILE_BYTES = 1_000_000  # 1 MB ceiling — GitHub event payloads are small


@dataclass(slots=True)
class DoctorCheck:
    """A single doctor check result."""

    name: str
    status: str
    detail: str
    remediation: str | None = None


@dataclass(slots=True)
class DoctorReport:
    """Aggregate doctor output."""

    checks: list[DoctorCheck]

    @property
    def exit_code(self) -> int:
        """Return `1` when any doctor check failed, else `0`."""
        return 1 if any(check.status == "FAIL" for check in self.checks) else 0


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in the target repo and capture text output."""
    env = os.environ.copy()
    env.update({
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_ASKPASS": "",
        "SSH_ASKPASS": "",
        "GIT_PAGER": "cat",
    })
    command = ["git", *args]
    try:
        return subprocess.run(
            command,
            cwd=repo_root,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=command,
            returncode=124,
            stdout="",
            stderr=f"git command timed out after {_GIT_TIMEOUT_SECONDS:.0f} seconds",
        )


def _git_timed_out(result: subprocess.CompletedProcess[str]) -> bool:
    """Return True when a git subprocess exceeded the safety timeout."""
    return result.returncode == 124 and "timed out" in (result.stderr or "").lower()


def _is_valid_branch_name(repo_root: Path, branch: str) -> bool:
    """Return True when `branch` is a valid branch-style ref name."""
    if not branch:
        return False
    result = _run_git(repo_root, "check-ref-format", "--branch", branch)
    return result.returncode == 0


def _git_ref_exists(repo_root: Path, ref_name: str) -> bool:
    """Return True when `ref_name` resolves to a commit in this repo."""
    result = _run_git(
        repo_root,
        "rev-parse",
        "--verify",
        "--quiet",
        "--end-of-options",
        f"{ref_name}^{{commit}}",
    )
    return result.returncode == 0


def _resolve_branch_target(repo_root: Path, branch: str) -> str | None:
    """Resolve a validated branch name to a local or remote-tracking ref."""
    if not _is_valid_branch_name(repo_root, branch):
        return None
    if _git_ref_exists(repo_root, branch):
        return branch
    remote_ref = f"origin/{branch}"
    if _git_ref_exists(repo_root, remote_ref):
        return remote_ref
    return None


def _read_event_file(path: str) -> dict | None:
    """Safely read a GitHub event JSON file, rejecting non-files and oversized inputs."""
    if not path:
        return None
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        return None
    try:
        if p.stat().st_size > _MAX_EVENT_FILE_BYTES:
            return None
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _extract_pr_number(event_path: str) -> int | None:
    payload = _read_event_file(event_path)
    if payload is None:
        return None

    if not isinstance(payload, dict):
        return None

    pr = payload.get("pull_request")
    if not isinstance(pr, dict):
        return None

    number = pr.get("number")
    if isinstance(number, bool):
        return None
    if isinstance(number, int) and number > 0:
        return number
    if isinstance(number, str) and number.isdigit():
        parsed = int(number)
        return parsed if parsed > 0 else None
    return None


def _configured_models(config: CouncilConfig) -> list[tuple[str, str]]:
    models = [("chair", config.chair_model)]
    models.extend((f"reviewer:{reviewer.id}", reviewer.model) for reviewer in config.active_reviewers)
    return models


def run_doctor(
    repo_root: Path | None = None,
    config: CouncilConfig | None = None,
    branch: str | None = None,
    audience: str | None = None,
    github_pr: bool = False,
) -> DoctorReport:
    """Run practical setup diagnostics for a Council invocation."""
    root = (repo_root or Path.cwd()).resolve()
    checks: list[DoctorCheck] = []

    if config is None:
        config = load_config(root)

    git_root_result = _run_git(root, "rev-parse", "--show-toplevel")
    in_git_repo = git_root_result.returncode == 0

    if _git_timed_out(git_root_result):
        checks.append(
            DoctorCheck(
                "git_repo",
                "FAIL",
                "Git probing timed out for the target repository.",
                remediation="Retry in a healthy local clone or use `--repo` only with trusted, responsive repositories.",
            )
        )
    elif in_git_repo:
        repo_path = git_root_result.stdout.strip()
        checks.append(DoctorCheck("git_repo", "PASS", f"Git repository detected at {repo_path}."))
    else:
        checks.append(
            DoctorCheck(
                "git_repo",
                "FAIL",
                "The target directory is not a git repository.",
                remediation="Run `council` inside a git repo or pass `--repo` with a repository root.",
            )
        )

    if in_git_repo:
        branch_result = _run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
        current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"
        if current_branch in {"HEAD", "unknown", ""}:
            checks.append(
                DoctorCheck(
                    "current_branch",
                    "WARN",
                    "Current branch is detached or unknown.",
                    remediation="Switch to a named branch before local review work when possible.",
                )
            )
        else:
            checks.append(
                DoctorCheck("current_branch", "PASS", f"Current branch is `{current_branch}`.")
            )

    if in_git_repo and branch:
        resolved_ref = _resolve_branch_target(root, branch)
        if resolved_ref:
            checks.append(
                DoctorCheck("diff_target", "PASS", f"Diff target `{branch}` resolves as `{resolved_ref}`.")
            )
        else:
            checks.append(
                DoctorCheck(
                    "diff_target",
                    "FAIL",
                    f"Diff target `{branch}` could not be resolved locally or as `origin/{branch}`.",
                    remediation="Fetch the target branch or pass a valid `--branch` value such as `main`.",
                )
            )
    elif in_git_repo:
        checks.append(
            DoctorCheck(
                "diff_target",
                "WARN",
                "No diff target branch was provided.",
                remediation="Use `council review --branch main` in local runs and `--ci --branch <base>` in CI.",
            )
        )

    resolved_audience = audience or config.presentation.default_audience or "developer"
    if resolved_audience in {"developer", "owner"}:
        checks.append(
            DoctorCheck("audience", "PASS", f"Resolved output audience is `{resolved_audience}`.")
        )
    else:
        checks.append(
            DoctorCheck(
                "audience",
                "FAIL",
                f"Resolved output audience `{resolved_audience}` is invalid.",
                remediation="Use `developer` or `owner` for the audience setting.",
            )
        )

    if config.active_reviewers:
        checks.append(
            DoctorCheck(
                "reviewers",
                "PASS",
                f"{len(config.active_reviewers)} active reviewer(s) configured.",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                "reviewers",
                "FAIL",
                "No active reviewers are configured.",
                remediation="Enable at least one reviewer in `.council.toml` before running `council review`.",
            )
        )

    _provider_key_names = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY")
    configured_key_count = sum(1 for k in _provider_key_names if os.getenv(k))
    if configured_key_count:
        checks.append(
            DoctorCheck(
                "api_keys",
                "PASS",
                f"At least one LLM provider API key detected ({configured_key_count} of {len(_provider_key_names)}).",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                "api_keys",
                "FAIL",
                "No LLM API keys were detected.",
                remediation="Set at least one of `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY`.",
            )
        )

    missing_provider_keys: list[str] = []
    fallback_likely_models: list[str] = []
    unknown_models: list[str] = []
    for label, model_name in _configured_models(config):
        env_var = provider_env_var_for_model(model_name)
        if env_var and not os.getenv(env_var):
            missing_provider_keys.append(f"{label} -> {model_name} requires `{env_var}`")

        support = classify_model_json_support(model_name)
        if support == "fallback_likely":
            fallback_likely_models.append(f"{label} -> {model_name}")
        elif support == "unknown":
            unknown_models.append(f"{label} -> {model_name}")

    if missing_provider_keys:
        checks.append(
            DoctorCheck(
                "model_keys",
                "FAIL",
                "Some configured models are missing their likely provider keys.",
                remediation="; ".join(missing_provider_keys),
            )
        )
    else:
        checks.append(
            DoctorCheck("model_keys", "PASS", "Configured models have matching known provider keys or use unknown providers.")
        )

    if fallback_likely_models:
        checks.append(
            DoctorCheck(
                "json_transport",
                "WARN",
                "Some configured models will likely need prompt-only JSON fallback.",
                remediation="; ".join(fallback_likely_models),
            )
        )
    elif unknown_models:
        checks.append(
            DoctorCheck(
                "json_transport",
                "WARN",
                "Could not determine native JSON-mode support for some configured models.",
                remediation="; ".join(unknown_models),
            )
        )
    else:
        checks.append(
            DoctorCheck("json_transport", "PASS", "Configured models likely support native JSON mode.")
        )

    if github_pr:
        repo = os.getenv("GITHUB_REPOSITORY")
        token = os.getenv("GITHUB_TOKEN")
        event_path = os.getenv("GITHUB_EVENT_PATH")
        missing = [
            name
            for name, value in (
                ("GITHUB_REPOSITORY", repo),
                ("GITHUB_TOKEN", token),
                ("GITHUB_EVENT_PATH", event_path),
            )
            if not value
        ]
        if missing:
            checks.append(
                DoctorCheck(
                    "github_pr",
                    "FAIL",
                    f"GitHub PR reporting context is incomplete: {', '.join(missing)}.",
                    remediation="Run inside a GitHub Actions pull_request job or unset `--github-pr` for local runs.",
                )
            )
        else:
            pr_number = _extract_pr_number(event_path)
            if pr_number is None:
                checks.append(
                    DoctorCheck(
                        "github_pr",
                        "FAIL",
                        "GitHub event payload does not contain a pull request number.",
                        remediation="Use `--github-pr` only for pull_request workflows with a valid `GITHUB_EVENT_PATH` payload.",
                    )
                )
            else:
                checks.append(
                    DoctorCheck(
                        "github_pr",
                        "PASS",
                        f"GitHub PR reporting context looks valid for PR #{pr_number}.",
                    )
                )

    return DoctorReport(checks=checks)

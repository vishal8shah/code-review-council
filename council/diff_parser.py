"""Git diff parser — converts raw diffs into structured DiffContext.

Uses the `unidiff` library for reliable unified diff parsing, with
fallback to git subprocess for obtaining the diff text itself.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from unidiff import PatchSet

from .schemas import DiffContext, DiffFile, DiffHunk

# Map file extensions to language names
EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".md": "markdown",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
}


def detect_language(file_path: str) -> str | None:
    """Detect language from file extension."""
    ext = Path(file_path).suffix.lower()
    return EXTENSION_MAP.get(ext)


def get_git_diff(
    repo_root: Path | None = None,
    staged: bool = False,
    branch: str | None = None,
) -> str:
    """Get git diff text via subprocess.

    Args:
        repo_root: Path to the repo. Defaults to cwd.
        staged: If True, diff staged changes (--cached).
        branch: If set, diff against this branch (e.g., "main").
            In CI checkouts the local ref may not exist; the function
            automatically retries with origin/<branch> before failing.

    Returns:
        Raw unified diff text.
    """
    cwd = repo_root or Path.cwd()
    cmd = ["git", "diff", "--unified=3"]

    if staged:
        cmd.append("--cached")
    elif branch:
        cmd.extend([f"{branch}...HEAD"])

    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

    if result.returncode != 0:
        # In CI checkouts the branch only exists as origin/<branch>.
        # Retry once with the remote-tracking ref before giving up.
        if branch and "unknown revision" in result.stderr:
            fallback_cmd = ["git", "diff", "--unified=3", f"origin/{branch}...HEAD"]
            fallback = subprocess.run(fallback_cmd, cwd=cwd, capture_output=True, text=True)
            if fallback.returncode == 0:
                return fallback.stdout
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")

    return result.stdout


def get_current_branch(repo_root: Path | None = None) -> str:
    """Get the current git branch name."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_root or Path.cwd(),
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def get_file_content(file_path: str, repo_root: Path | None = None) -> str | None:
    """Read the current content of a file (for AST analysis).

    Validates the resolved path stays within repo_root to prevent
    path traversal from crafted diff content.
    """
    root = (repo_root or Path.cwd()).resolve()
    full_path = (root / file_path).resolve()

    # Security: ensure resolved path is inside repo root
    if not full_path.is_relative_to(root):
        return None

    if full_path.exists():
        try:
            return full_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return None
    return None


def parse_diff(
    diff_text: str,
    repo_root: Path | None = None,
    load_content: bool = True,
) -> DiffContext:
    """Parse a unified diff string into a structured DiffContext.

    Args:
        diff_text: Raw unified diff text.
        repo_root: Repo root for loading file contents.
        load_content: If True, load full file content for AST analysis.

    Returns:
        Structured DiffContext with per-file, per-hunk data.
    """
    if not diff_text.strip():
        return DiffContext()

    patch = PatchSet(diff_text)

    files: list[DiffFile] = []
    changed_files: list[str] = []
    added_files: list[str] = []
    deleted_files: list[str] = []
    total_additions = 0
    total_deletions = 0

    for patched_file in patch:
        file_path = patched_file.path

        # Determine change type
        if patched_file.is_added_file:
            change_type = "added"
            added_files.append(file_path)
        elif patched_file.is_removed_file:
            change_type = "deleted"
            deleted_files.append(file_path)
        elif patched_file.is_rename:
            change_type = "renamed"
        else:
            change_type = "modified"

        changed_files.append(file_path)

        # Parse hunks
        hunks: list[DiffHunk] = []
        for hunk in patched_file:
            hunks.append(
                DiffHunk(
                    source_start=hunk.source_start,
                    source_length=hunk.source_length,
                    target_start=hunk.target_start,
                    target_length=hunk.target_length,
                    content=str(hunk),
                )
            )

        additions = patched_file.added
        deletions = patched_file.removed
        total_additions += additions
        total_deletions += deletions

        # Optionally load file content for AST analysis
        source_content = None
        if load_content and change_type != "deleted":
            source_content = get_file_content(file_path, repo_root)

        files.append(
            DiffFile(
                path=file_path,
                language=detect_language(file_path),
                change_type=change_type,
                additions=additions,
                deletions=deletions,
                hunks=hunks,
                source_content=source_content,
            )
        )

    return DiffContext(
        files=files,
        changed_files=changed_files,
        added_files=added_files,
        deleted_files=deleted_files,
        branch=get_current_branch(repo_root),
        total_additions=total_additions,
        total_deletions=total_deletions,
    )

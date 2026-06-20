"""Repository discovery helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


class RepoResolutionError(RuntimeError):
    """Raised when the current directory is not inside a git worktree."""


def resolve_repo_root(cwd: Path | None = None) -> Path:
    """Return the absolute git worktree root for ``cwd``."""

    working_directory = cwd or Path.cwd()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=working_directory,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "not inside a git repository"
        raise RepoResolutionError(message)

    return Path(result.stdout.strip()).resolve()


@dataclass(frozen=True)
class GitFileChange:
    """One changed file reported by git status."""

    path: str
    status_code: str
    category: str


@dataclass(frozen=True)
class GitDiffStat:
    """Line-level diff statistics for a git worktree."""

    files_changed: int
    additions: int
    deletions: int


def list_file_changes(repo_root: Path) -> list[GitFileChange]:
    """Return changed files using stable porcelain output."""

    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "unable to read git status"
        raise RepoResolutionError(message)

    changes: list[GitFileChange] = []
    for line in result.stdout.splitlines():
        if not line:
            continue

        status_code = line[:2]
        path = line[3:]
        if is_internal_state_path(path):
            continue

        changes.append(
            GitFileChange(
                path=path,
                status_code=status_code,
                category=categorize_status(status_code),
            )
        )

    return changes


def is_internal_state_path(path: str) -> bool:
    """Return whether a path belongs to AgentFlightRecorder local state."""

    return path == ".afr" or path.startswith(".afr/")


def read_diff_stat(repo_root: Path) -> GitDiffStat:
    """Return aggregate added/deleted line counts for tracked changes."""

    result = subprocess.run(
        ["git", "diff", "--numstat", "HEAD", "--"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return GitDiffStat(files_changed=0, additions=0, deletions=0)

    files_changed = 0
    additions = 0
    deletions = 0
    for line in result.stdout.splitlines():
        parts = line.split("\t", maxsplit=2)
        if len(parts) < 3:
            continue

        added, removed, _path = parts
        files_changed += 1
        additions += parse_numstat_count(added)
        deletions += parse_numstat_count(removed)

    return GitDiffStat(
        files_changed=files_changed,
        additions=additions,
        deletions=deletions,
    )


def categorize_status(status_code: str) -> str:
    """Map porcelain status codes to coarse categories for reports."""

    if status_code == "??":
        return "untracked"
    if "D" in status_code:
        return "deleted"
    if "R" in status_code:
        return "renamed"
    if "A" in status_code:
        return "added"
    if "M" in status_code:
        return "modified"
    if "U" in status_code:
        return "conflicted"

    return "changed"


def parse_numstat_count(value: str) -> int:
    """Parse git numstat counts, treating binary markers as zero."""

    if value == "-":
        return 0

    return int(value)

"""Repository discovery helpers."""

from __future__ import annotations

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

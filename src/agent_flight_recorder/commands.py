"""Command execution helpers and heuristics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import Sequence
from io import TextIOBase
from pathlib import Path
import shlex
import subprocess
import threading
import time


class InvalidCommandError(ValueError):
    """Raised when ``afr run`` does not receive a command to execute."""


@dataclass(frozen=True)
class CommandExecution:
    """One completed command execution."""

    argv: list[str]
    command_text: str
    cwd: Path
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    exit_code: int
    command_kind: str
    stdout: str
    stderr: str


def normalize_command_args(command_args: Sequence[str]) -> list[str]:
    """Normalize ``afr run`` arguments into a command argv list."""

    argv = list(command_args)
    if argv and argv[0] == "--":
        argv = argv[1:]

    if not argv:
        raise InvalidCommandError("no command provided")

    return argv


def format_command(argv: Sequence[str]) -> str:
    """Return a shell-safe string form of ``argv``."""

    return shlex.join(argv)


def detect_command_kind(argv: Sequence[str]) -> str:
    """Return a coarse command category for reporting heuristics."""

    normalized = [token.lower() for token in argv]
    token_set = set(normalized)

    if has_any_token(token_set, {"pytest", "py.test", "unittest", "nosetests", "tox", "nox"}):
        return "test"
    if "test" in token_set and has_any_token(token_set, {"npm", "pnpm", "yarn", "bun", "go"}):
        return "test"
    if has_any_token(token_set, {"build", "compile", "package", "dist"}):
        return "build"
    if has_any_token(token_set, {"ruff", "flake8", "eslint", "mypy", "pyright", "lint", "check"}):
        return "check"
    if has_any_token(token_set, {"black", "prettier", "isort", "format", "fmt"}):
        return "format"
    if has_any_token(token_set, {"pip", "pip3", "poetry", "uv", "npm", "pnpm", "yarn", "bun"}):
        if has_any_token(token_set, {"install", "add", "sync"}):
            return "install"

    return "other"


def has_any_token(values: set[str], expected: set[str]) -> bool:
    """Return whether any expected token appears in the command token set."""

    return not values.isdisjoint(expected)


def relativize_cwd(cwd: Path, repo_root: Path) -> str:
    """Render a working directory relative to the repository when possible."""

    resolved_cwd = cwd.resolve()
    resolved_root = repo_root.resolve()
    if resolved_cwd == resolved_root:
        return "."

    try:
        return str(resolved_cwd.relative_to(resolved_root))
    except ValueError:
        return str(resolved_cwd)


def execute_command(argv: Sequence[str], *, cwd: Path) -> CommandExecution:
    """Execute ``argv`` while mirroring output to the current terminal."""

    resolved_cwd = cwd.resolve()
    normalized_argv = list(argv)
    command_text = format_command(normalized_argv)
    command_kind = detect_command_kind(normalized_argv)
    started_at = datetime.now(timezone.utc).replace(microsecond=0)
    started_monotonic = time.monotonic()

    try:
        process = subprocess.Popen(
            normalized_argv,
            cwd=resolved_cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as error:
        message = f"{error.strerror}: {error.filename}\n"
        return _build_failed_start_result(
            argv=normalized_argv,
            command_text=command_text,
            cwd=resolved_cwd,
            started_at=started_at,
            duration_ms=0,
            command_kind=command_kind,
            exit_code=127,
            stderr=message,
        )
    except PermissionError as error:
        message = f"{error.strerror}: {error.filename}\n"
        return _build_failed_start_result(
            argv=normalized_argv,
            command_text=command_text,
            cwd=resolved_cwd,
            started_at=started_at,
            duration_ms=0,
            command_kind=command_kind,
            exit_code=126,
            stderr=message,
        )

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    stdout_thread = threading.Thread(
        target=_consume_stream,
        args=(process.stdout, stdout_chunks, TextIOBaseWriter.from_stream()),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_consume_stream,
        args=(process.stderr, stderr_chunks, TextIOBaseWriter.from_stream(stderr=True)),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    exit_code = process.wait()
    stdout_thread.join()
    stderr_thread.join()

    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    finished_at = datetime.now(timezone.utc).replace(microsecond=0)
    return CommandExecution(
        argv=normalized_argv,
        command_text=command_text,
        cwd=resolved_cwd,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        exit_code=exit_code,
        command_kind=command_kind,
        stdout="".join(stdout_chunks),
        stderr="".join(stderr_chunks),
    )


def _build_failed_start_result(
    *,
    argv: list[str],
    command_text: str,
    cwd: Path,
    started_at: datetime,
    duration_ms: int,
    command_kind: str,
    exit_code: int,
    stderr: str,
) -> CommandExecution:
    writer = TextIOBaseWriter.from_stream(stderr=True)
    writer.write(stderr)
    writer.flush()
    return CommandExecution(
        argv=argv,
        command_text=command_text,
        cwd=cwd,
        started_at=started_at,
        finished_at=started_at,
        duration_ms=duration_ms,
        exit_code=exit_code,
        command_kind=command_kind,
        stdout="",
        stderr=stderr,
    )


def _consume_stream(
    stream: TextIOBase | None,
    chunks: list[str],
    writer: "TextIOBaseWriter",
) -> None:
    """Mirror a subprocess stream while collecting the full text."""

    if stream is None:
        return

    try:
        for line in iter(stream.readline, ""):
            chunks.append(line)
            writer.write(line)
            writer.flush()
    finally:
        stream.close()


class TextIOBaseWriter:
    """Light wrapper for the current process stdout/stderr."""

    def __init__(self, stream: TextIOBase) -> None:
        self.stream = stream

    @classmethod
    def from_stream(cls, *, stderr: bool = False) -> "TextIOBaseWriter":
        import sys

        return cls(sys.stderr if stderr else sys.stdout)

    def write(self, value: str) -> None:
        self.stream.write(value)

    def flush(self) -> None:
        self.stream.flush()

from pathlib import Path

import pytest

from agent_flight_recorder.commands import (
    InvalidCommandError,
    detect_command_kind,
    normalize_command_args,
    relativize_cwd,
)


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["python", "-m", "pytest", "-q"], "test"),
        (["npm", "test"], "test"),
        (["python", "-m", "build"], "build"),
        (["ruff", "check", "."], "check"),
        (["black", "."], "format"),
        (["uv", "sync"], "install"),
        (["python", "script.py"], "other"),
    ],
)
def test_detect_command_kind(argv: list[str], expected: str):
    assert detect_command_kind(argv) == expected


def test_normalize_command_args_strips_separator():
    assert normalize_command_args(["--", "python", "-m", "pytest"]) == ["python", "-m", "pytest"]


def test_normalize_command_args_requires_command():
    with pytest.raises(InvalidCommandError):
        normalize_command_args([])


def test_relativize_cwd_prefers_repo_relative_paths(tmp_path: Path):
    nested = tmp_path / "src" / "package"
    nested.mkdir(parents=True)

    assert relativize_cwd(tmp_path, tmp_path) == "."
    assert relativize_cwd(nested, tmp_path) == "src/package"

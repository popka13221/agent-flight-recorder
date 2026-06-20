from pathlib import Path
import subprocess

from agent_flight_recorder.cli import main


def test_help_prints_command_list(capsys):
    exit_code = main([])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Local flight recorder" in captured.out
    assert "start" in captured.out
    assert "current" in captured.out
    assert "commit-msg" in captured.out


def test_planned_command_exits_with_clear_message(capsys):
    exit_code = main(["status"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "planned but not implemented yet" in captured.err


def test_start_current_stop_session(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    start_exit = main(["start"])
    start_output = capsys.readouterr()

    assert start_exit == 0
    assert "Started session 1." in start_output.out
    assert str(tmp_path / ".afr" / "flight_recorder.db") in start_output.out

    current_exit = main(["current"])
    current_output = capsys.readouterr()

    assert current_exit == 0
    assert "Active session 1." in current_output.out

    stop_exit = main(["stop"])
    stop_output = capsys.readouterr()

    assert stop_exit == 0
    assert "Stopped session 1." in stop_output.out
    assert "Stopped:" in stop_output.out
    assert main(["timeline"]) == 0

    timeline_output = capsys.readouterr()
    assert "Timeline for session 1 (stopped)" in timeline_output.out
    assert "session_started" in timeline_output.out
    assert "session_stopped" in timeline_output.out


def test_current_without_active_session_returns_error(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["current"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "no active session" in captured.err


def test_start_rejects_second_active_session(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(["start"]) == 0
    capsys.readouterr()

    exit_code = main(["start"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "already active" in captured.err


def test_timeline_rejects_unknown_session(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["timeline", "--session", "42"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "session 42 was not found" in captured.err


def test_timeline_requires_at_least_one_recorded_session(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["timeline"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "no recorded sessions" in captured.err


def init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)

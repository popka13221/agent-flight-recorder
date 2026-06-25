from pathlib import Path
import json
import subprocess
import sys

from agent_flight_recorder.cli import main


def test_help_prints_command_list(capsys):
    exit_code = main([])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Local flight recorder" in captured.out
    assert "start" in captured.out
    assert "current" in captured.out
    assert "commit-msg" in captured.out
    assert "mcp" in captured.out


def test_commit_msg_requires_repository_changes(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["commit-msg"])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "no repository changes detected" in captured.err


def test_run_requires_a_command(capsys):
    exit_code = main(["run"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "no command provided" in captured.err


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


def test_status_summarizes_worktree_without_active_session(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("draft\n", encoding="utf-8")

    exit_code = main(["status"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert f"Repo: {tmp_path}" in captured.out
    assert "Active session: -" in captured.out
    assert "Files changed: 1" in captured.out
    assert "Risk findings: 0" in captured.out
    assert "notes.txt" in captured.out


def test_snapshot_requires_active_session(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["snapshot"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "no active session" in captured.err


def test_snapshot_records_worktree_state_in_timeline(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("draft\n", encoding="utf-8")

    assert main(["start"]) == 0
    capsys.readouterr()

    exit_code = main(["snapshot"])
    snapshot_output = capsys.readouterr()

    assert exit_code == 0
    assert "Recorded snapshot 1 for session 1." in snapshot_output.out
    assert "Files changed: 1" in snapshot_output.out
    assert "Risk findings: 0" in snapshot_output.out

    assert main(["timeline"]) == 0
    timeline_output = capsys.readouterr()
    assert "snapshot_recorded" in timeline_output.out


def test_status_and_report_surface_missing_test_risk(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "src" / "agent_flight_recorder"
    source_dir.mkdir(parents=True)
    (source_dir / "cli.py").write_text("print('hello')\n", encoding="utf-8")

    assert main(["start"]) == 0
    capsys.readouterr()

    assert main(["status"]) == 0
    status_output = capsys.readouterr()
    assert "Risk findings: 1" in status_output.out
    assert "Source changes do not include nearby test updates." in status_output.out

    assert main(["snapshot"]) == 0
    capsys.readouterr()

    assert main(["report"]) == 0
    report_output = capsys.readouterr()
    assert "Risks:" in report_output.out
    assert "Review recorder risk findings before handoff." in report_output.out


def test_run_requires_active_session(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["run", "--", sys.executable, "-c", "print('hello')"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "no active session" in captured.err


def test_run_records_successful_command_and_status_summary(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(["start"]) == 0
    capsys.readouterr()

    exit_code = main(
        [
            "run",
            "--",
            sys.executable,
            "-c",
            "print('stdout line'); import sys; print('stderr line', file=sys.stderr)",
        ]
    )
    run_output = capsys.readouterr()

    assert exit_code == 0
    assert "stdout line" in run_output.out
    assert "Recorded command 1 for session 1." in run_output.out
    assert "Kind: other" in run_output.out
    assert "stderr line" in run_output.err

    assert main(["status"]) == 0
    status_output = capsys.readouterr()
    assert "Commands recorded: 1" in status_output.out
    assert "Latest command: other exit 0" in status_output.out

    assert main(["timeline"]) == 0
    timeline_output = capsys.readouterr()
    assert "command_succeeded" in timeline_output.out


def test_run_records_failed_test_command(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(["start"]) == 0
    capsys.readouterr()

    exit_code = main(["run", "--", sys.executable, "-m", "pytest", "--version"])
    run_output = capsys.readouterr()

    assert exit_code == 0
    assert "Kind: test" in run_output.out

    exit_code = main(
        [
            "run",
            "--",
            sys.executable,
            "-c",
            "import sys; print('boom', file=sys.stderr); raise SystemExit(3)",
        ]
    )
    failed_output = capsys.readouterr()

    assert exit_code == 3
    assert "boom" in failed_output.err
    assert "Exit: 3" in failed_output.out

    assert main(["status"]) == 0
    status_output = capsys.readouterr()
    assert "Commands recorded: 2" in status_output.out
    assert "Recent failed commands:" in status_output.out
    assert "exit 3" in status_output.out

    assert main(["timeline"]) == 0
    timeline_output = capsys.readouterr()
    assert "command_failed" in timeline_output.out


def test_report_requires_recorded_session(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["report"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "no recorded sessions" in captured.err


def test_report_renders_text_markdown_and_json(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(["start"]) == 0
    capsys.readouterr()
    (tmp_path / "notes.txt").write_text("draft\n", encoding="utf-8")
    assert main(["snapshot"]) == 0
    capsys.readouterr()
    assert main(["run", "--", sys.executable, "-c", "print('ok')"]) == 0
    capsys.readouterr()

    assert main(["report"]) == 0
    text_output = capsys.readouterr()
    assert "Session 1 report" in text_output.out
    assert "Snapshot 1: 1 files changed" in text_output.out
    assert "other exit 0" in text_output.out

    assert main(["report", "--md"]) == 0
    markdown_output = capsys.readouterr()
    assert "# AgentFlightRecorder Session 1" in markdown_output.out
    assert "## Next Checks" in markdown_output.out

    assert main(["report", "--json"]) == 0
    json_output = capsys.readouterr()
    payload = json.loads(json_output.out)
    assert payload["session"]["id"] == 1
    assert payload["snapshot"]["files_changed"] == 1
    assert payload["commands"][0]["exit_code"] == 0


def test_commit_msg_renders_text_and_json(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(["start"]) == 0
    capsys.readouterr()

    source_dir = tmp_path / "src" / "agent_flight_recorder"
    source_dir.mkdir(parents=True)
    (source_dir / "commit_messages.py").write_text("FEATURE = True\n", encoding="utf-8")

    assert main(["run", "--", sys.executable, "-m", "pytest", "--version"]) == 0
    capsys.readouterr()

    assert main(["commit-msg"]) == 0
    text_output = capsys.readouterr()
    assert "Primary suggestion:" in text_output.out
    assert "feat(commit-msg): add commit message suggestions" in text_output.out
    assert "Warnings:" not in text_output.out

    assert main(["commit-msg", "--json"]) == 0
    json_output = capsys.readouterr()
    payload = json.loads(json_output.out)
    assert payload["primary"]["type"] == "feat"
    assert payload["primary"]["scope"] == "commit-msg"
    assert payload["evidence"]["successful_verifications"] == 1


def init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)

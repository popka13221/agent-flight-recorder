from datetime import datetime, timezone
from pathlib import Path
import subprocess

from agent_flight_recorder.session_data import (
    build_changed_files_payload,
    build_command_history_payload,
    build_current_session_payload,
    build_risk_report_payload,
    build_session_summary_payload,
)
from agent_flight_recorder.store import RecorderStore


def test_session_data_returns_empty_payloads_without_recorded_sessions(tmp_path: Path):
    init_repo(tmp_path)
    store = RecorderStore.open_for_repo(tmp_path)

    current = build_current_session_payload(store)
    commands = build_command_history_payload(store)
    summary = build_session_summary_payload(store)

    assert current["session"] is None
    assert current["message"] == "No recorded sessions."
    assert commands["commands"] == []
    assert commands["message"] == "No recorded sessions."
    assert summary["session"] is None
    assert summary["message"] == "No recorded sessions."


def test_session_data_reads_live_changes_and_risks(tmp_path: Path):
    init_repo(tmp_path)
    store = RecorderStore.open_for_repo(tmp_path)
    source_dir = tmp_path / "src" / "agent_flight_recorder"
    source_dir.mkdir(parents=True)
    (source_dir / "mcp_server.py").write_text("FEATURE = True\n", encoding="utf-8")

    changed = build_changed_files_payload(store)
    risks = build_risk_report_payload(store)

    assert changed["source"] == "live"
    assert changed["files"][0]["path"] == "src/agent_flight_recorder/mcp_server.py"
    assert risks["source"] == "live"
    assert risks["risks"][0]["code"] == "missing-tests"


def test_session_data_summarizes_snapshot_and_commands(tmp_path: Path):
    init_repo(tmp_path)
    store = RecorderStore.open_for_repo(tmp_path)
    session = store.start_session()
    store.record_snapshot(
        session_id=session.id,
        files_changed=1,
        additions=8,
        deletions=2,
        payload={
            "files": [
                {
                    "path": "src/agent_flight_recorder/mcp_server.py",
                    "status": " M",
                    "category": "modified",
                }
            ],
            "risks": [
                {
                    "code": "missing-tests",
                    "severity": "medium",
                    "summary": "Source changes do not include nearby test updates.",
                    "detail": "Review whether changed modules need coverage updates: mcp_server.",
                    "paths": ["mcp_server"],
                }
            ],
        },
    )
    timestamp = datetime(2026, 6, 25, 8, 0, tzinfo=timezone.utc)
    store.record_command(
        session_id=session.id,
        started_at=timestamp,
        finished_at=timestamp,
        duration_ms=18,
        command_text="python -m pytest -q",
        argv=["python", "-m", "pytest", "-q"],
        cwd=tmp_path,
        exit_code=0,
        command_kind="test",
        stdout="ok\n",
        stderr="",
    )

    changed = build_changed_files_payload(store, source="snapshot")
    commands = build_command_history_payload(store, limit=5)
    summary = build_session_summary_payload(store)

    assert changed["snapshot"]["files_changed"] == 1
    assert changed["files"][0]["path"] == "src/agent_flight_recorder/mcp_server.py"
    assert commands["total_commands"] == 1
    assert commands["commands"][0]["stdout"] == "ok\n"
    assert summary["latest_snapshot"]["additions"] == 8
    assert summary["latest_command"]["kind"] == "test"
    assert summary["risks"][0]["code"] == "missing-tests"


def init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)

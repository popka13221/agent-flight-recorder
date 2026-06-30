from datetime import datetime, timezone
from pathlib import Path

from agent_flight_recorder.reports import build_session_report
from agent_flight_recorder.store import RecorderStore
from agent_flight_recorder.terminal_ui import render_terminal_dashboard


def test_terminal_dashboard_renders_session_overview(tmp_path: Path):
    store = RecorderStore.open_for_repo(tmp_path)
    session = store.start_session()
    store.record_snapshot(
        session_id=session.id,
        files_changed=3,
        additions=12,
        deletions=4,
        payload={"files": []},
    )
    timestamp = datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc)
    store.record_command(
        session_id=session.id,
        started_at=timestamp,
        finished_at=timestamp,
        duration_ms=17,
        command_text="python -m pytest -q",
        argv=["python", "-m", "pytest", "-q"],
        cwd=tmp_path,
        exit_code=0,
        command_kind="test",
        stdout="passed\n",
        stderr="",
    )

    report = build_session_report(store, session)
    dashboard = render_terminal_dashboard(report, repo_root=tmp_path)

    assert "AgentFlightRecorder" in dashboard
    assert "Session: 1 (active)" in dashboard
    assert "Snapshot" in dashboard
    assert "files: 3" in dashboard
    assert "diff: +12/-4" in dashboard
    assert "Commands" in dashboard
    assert "test    exit 0" in dashboard
    assert "Next checks" in dashboard

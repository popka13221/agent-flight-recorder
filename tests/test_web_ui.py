from datetime import datetime, timezone
from pathlib import Path

from agent_flight_recorder.reports import build_session_report
from agent_flight_recorder.store import RecorderStore
from agent_flight_recorder.web_ui import load_dashboard_html, render_web_dashboard


def test_web_dashboard_renders_session_and_escapes_command_text(tmp_path: Path):
    store = RecorderStore.open_for_repo(tmp_path)
    session = store.start_session()
    store.record_snapshot(
        session_id=session.id,
        files_changed=1,
        additions=2,
        deletions=0,
        payload={"files": []},
    )
    timestamp = datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc)
    store.record_command(
        session_id=session.id,
        started_at=timestamp,
        finished_at=timestamp,
        duration_ms=11,
        command_text="python -c \"print('<ok>')\"",
        argv=["python", "-c", "print('<ok>')"],
        cwd=tmp_path,
        exit_code=0,
        command_kind="test",
        stdout="",
        stderr="",
    )

    report = build_session_report(store, session)
    html = render_web_dashboard(report, repo_root=tmp_path)

    assert "<!doctype html>" in html
    assert "AgentFlightRecorder" in html
    assert "Session 1" in html
    assert "<strong class=\"metric\">1</strong>" in html
    assert "&lt;ok&gt;" in html
    assert "Next Checks" in html


def test_load_dashboard_html_uses_latest_session(tmp_path: Path):
    store = RecorderStore.open_for_repo(tmp_path)
    session = store.start_session()

    html = load_dashboard_html(tmp_path, session_id=None)

    assert f"Session {session.id}" in html


def test_load_dashboard_html_rejects_missing_session(tmp_path: Path):
    RecorderStore.open_for_repo(tmp_path)

    try:
        load_dashboard_html(tmp_path, session_id=404)
    except LookupError as error:
        assert "session 404 was not found" in str(error)
    else:
        raise AssertionError("expected LookupError")

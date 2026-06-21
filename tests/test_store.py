from pathlib import Path

import pytest

from agent_flight_recorder.store import ActiveSessionError, NoActiveSessionError, RecorderStore, utc_now


def test_store_starts_and_stops_sessions(tmp_path: Path):
    store = RecorderStore.open_for_repo(tmp_path)

    started = store.start_session()

    assert started.id > 0
    assert started.repo_root == tmp_path
    assert started.status == "active"
    assert store.get_active_session() == started

    stopped = store.stop_active_session()

    assert stopped.id == started.id
    assert stopped.status == "stopped"
    assert stopped.stopped_at is not None
    assert store.get_active_session() is None

    events = store.list_events(started.id)
    assert [event.event_type for event in events] == ["session_started", "session_stopped"]


def test_store_rejects_multiple_active_sessions(tmp_path: Path):
    store = RecorderStore.open_for_repo(tmp_path)
    first = store.start_session()

    with pytest.raises(ActiveSessionError) as error:
        store.start_session()

    assert error.value.session_id == first.id


def test_store_requires_active_session_to_stop(tmp_path: Path):
    store = RecorderStore.open_for_repo(tmp_path)

    with pytest.raises(NoActiveSessionError):
        store.stop_active_session()


def test_store_records_snapshots_and_timeline_events(tmp_path: Path):
    store = RecorderStore.open_for_repo(tmp_path)
    session = store.start_session()

    snapshot = store.record_snapshot(
        session_id=session.id,
        files_changed=2,
        additions=10,
        deletions=3,
        payload={
            "files": [
                {"path": "README.md", "category": "modified", "status": " M"},
                {"path": "notes.txt", "category": "untracked", "status": "??"},
            ]
        },
    )

    assert snapshot.session_id == session.id
    assert snapshot.files_changed == 2
    assert snapshot.additions == 10
    assert snapshot.deletions == 3
    assert snapshot.payload["files"][0]["path"] == "README.md"
    assert store.get_latest_snapshot(session.id) == snapshot
    assert store.list_snapshots(session.id) == [snapshot]

    events = store.list_events(session.id)
    assert [event.event_type for event in events] == ["session_started", "snapshot_recorded"]
    assert events[-1].detail == "2 files changed, +10/-3"


def test_store_records_commands_and_failed_command_queries(tmp_path: Path):
    store = RecorderStore.open_for_repo(tmp_path)
    session = store.start_session()
    started_at = utc_now()
    finished_at = utc_now()

    failed = store.record_command(
        session_id=session.id,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=123,
        command_text="python -m pytest -q",
        argv=["python", "-m", "pytest", "-q"],
        cwd=tmp_path,
        exit_code=1,
        command_kind="test",
        stdout="collected 1 item\n",
        stderr="E   AssertionError\n",
    )
    passed = store.record_command(
        session_id=session.id,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=45,
        command_text="ruff check .",
        argv=["ruff", "check", "."],
        cwd=tmp_path,
        exit_code=0,
        command_kind="check",
        stdout="All checks passed!\n",
        stderr="",
    )

    assert store.count_commands(session.id) == 2
    assert store.get_command(failed.id) == failed
    assert store.get_latest_command(session.id) == passed
    assert store.list_commands(session.id) == [passed, failed]
    assert store.list_failed_commands(session.id) == [failed]

    events = store.list_events(session.id)
    assert [event.event_type for event in events] == [
        "session_started",
        "command_failed",
        "command_succeeded",
    ]
    assert "python -m pytest -q" in events[1].detail

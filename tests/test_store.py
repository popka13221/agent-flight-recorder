from pathlib import Path

import pytest

from agent_flight_recorder.store import ActiveSessionError, NoActiveSessionError, RecorderStore


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

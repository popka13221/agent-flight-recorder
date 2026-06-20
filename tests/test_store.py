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

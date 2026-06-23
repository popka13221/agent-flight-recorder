from datetime import datetime, timezone
from pathlib import Path
import json

from agent_flight_recorder.reports import (
    build_session_report,
    render_json_report,
    render_markdown_report,
    render_text_report,
)
from agent_flight_recorder.store import RecorderStore


def test_report_renders_snapshot_commands_and_next_checks(tmp_path: Path):
    store = RecorderStore.open_for_repo(tmp_path)
    session = store.start_session()
    store.record_snapshot(
        session_id=session.id,
        files_changed=2,
        additions=5,
        deletions=1,
        payload={
            "files": [{"path": "README.md", "category": "modified"}],
            "risks": [
                {
                    "code": "missing-tests",
                    "severity": "medium",
                    "summary": "Source changes do not include nearby test updates.",
                    "detail": "Review whether changed modules need coverage updates: reports.",
                    "paths": ["reports"],
                }
            ],
        },
    )
    timestamp = datetime(2026, 6, 22, 8, 0, tzinfo=timezone.utc)
    store.record_command(
        session_id=session.id,
        started_at=timestamp,
        finished_at=timestamp,
        duration_ms=12,
        command_text="python -m pytest -q",
        argv=["python", "-m", "pytest", "-q"],
        cwd=tmp_path,
        exit_code=0,
        command_kind="test",
        stdout="passed\n",
        stderr="",
    )

    report = build_session_report(store, session)

    text = render_text_report(report, repo_root=tmp_path)
    markdown = render_markdown_report(report, repo_root=tmp_path)
    json_payload = json.loads(render_json_report(report, repo_root=tmp_path))

    assert "Session 1 report" in text
    assert "Snapshot 1: 2 files changed, +5/-1" in text
    assert "[medium] Source changes do not include nearby test updates." in text
    assert "test exit 0" in text
    assert "Review recorder risk findings before handoff." in text

    assert "# AgentFlightRecorder Session 1" in markdown
    assert "## Risks" in markdown
    assert "- `test exit 0" in markdown

    assert json_payload["session"]["id"] == 1
    assert json_payload["snapshot"]["files_changed"] == 2
    assert json_payload["risks"][0]["code"] == "missing-tests"
    assert json_payload["commands"][0]["kind"] == "test"


def test_report_suggests_snapshot_and_command_evidence(tmp_path: Path):
    store = RecorderStore.open_for_repo(tmp_path)
    session = store.start_session()

    report = build_session_report(store, session)

    assert report.next_checks == [
        "Run `afr snapshot` to capture the current worktree state.",
        "Run tests or build checks through `afr run`.",
    ]


def test_report_surfaces_failed_commands(tmp_path: Path):
    store = RecorderStore.open_for_repo(tmp_path)
    session = store.start_session()
    timestamp = datetime(2026, 6, 22, 8, 0, tzinfo=timezone.utc)
    store.record_command(
        session_id=session.id,
        started_at=timestamp,
        finished_at=timestamp,
        duration_ms=25,
        command_text="python -m pytest",
        argv=["python", "-m", "pytest"],
        cwd=tmp_path,
        exit_code=2,
        command_kind="test",
        stdout="",
        stderr="failed\n",
    )

    report = build_session_report(store, session)
    text = render_text_report(report, repo_root=tmp_path)
    markdown = render_markdown_report(report, repo_root=tmp_path)

    assert "Risks:" in text
    assert "No risk findings." in text
    assert "Failed commands:" in text
    assert "test exit 2" in text
    assert "Investigate failed commands before committing or pushing." in text
    assert "## Failed Commands" in markdown

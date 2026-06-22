from datetime import datetime, timezone
import json
from pathlib import Path

from agent_flight_recorder.commit_messages import (
    CommitFileChange,
    build_commit_message_report,
    render_json_commit_message_report,
    render_text_commit_message_report,
)
from agent_flight_recorder.store import RecorderStore


def test_commit_message_report_prefers_feature_for_new_source_module(tmp_path: Path):
    store = RecorderStore.open_for_repo(tmp_path)
    session = store.start_session()
    timestamp = datetime(2026, 6, 22, 9, 0, tzinfo=timezone.utc)
    store.record_command(
        session_id=session.id,
        started_at=timestamp,
        finished_at=timestamp,
        duration_ms=34,
        command_text="python -m pytest -q",
        argv=["python", "-m", "pytest", "-q"],
        cwd=tmp_path,
        exit_code=0,
        command_kind="test",
        stdout="passed\n",
        stderr="",
    )

    report = build_commit_message_report(
        changes=[
            CommitFileChange(
                path="src/agent_flight_recorder/commit_messages.py",
                status_code="A ",
                category="added",
            ),
            CommitFileChange(path="src/agent_flight_recorder/cli.py", status_code=" M", category="modified"),
            CommitFileChange(path="tests/test_commit_messages.py", status_code="A ", category="added"),
        ],
        additions=120,
        deletions=8,
        commands=store.list_commands(session.id),
    )

    assert report.primary.message == "feat(commit-msg): add commit message suggestions"
    assert report.primary.confidence == "high"
    assert report.alternatives[0].type == "refactor"
    assert report.changelog == "- Add commit message suggestions."
    assert report.warnings == []

    text = render_text_commit_message_report(report)
    payload = json.loads(render_json_commit_message_report(report))

    assert "Primary suggestion:" in text
    assert "feat(commit-msg): add commit message suggestions" in text
    assert payload["primary"]["scope"] == "commit-msg"
    assert payload["evidence"]["successful_verifications"] == 1


def test_commit_message_report_prefers_docs_for_docs_only_changes():
    report = build_commit_message_report(
        changes=[
            CommitFileChange(path="README.md", status_code=" M", category="modified"),
            CommitFileChange(path="ROADMAP.md", status_code=" M", category="modified"),
        ],
        additions=18,
        deletions=4,
        commands=[],
    )

    assert report.primary.type == "docs"
    assert report.primary.scope == "docs"
    assert report.primary.description == "document project documentation"
    assert report.warnings == []


def test_commit_message_report_prefers_fix_after_failure_then_success(tmp_path: Path):
    store = RecorderStore.open_for_repo(tmp_path)
    session = store.start_session()
    timestamp = datetime(2026, 6, 22, 9, 0, tzinfo=timezone.utc)
    store.record_command(
        session_id=session.id,
        started_at=timestamp,
        finished_at=timestamp,
        duration_ms=40,
        command_text="python -m pytest -q",
        argv=["python", "-m", "pytest", "-q"],
        cwd=tmp_path,
        exit_code=1,
        command_kind="test",
        stdout="",
        stderr="F\n",
    )
    store.record_command(
        session_id=session.id,
        started_at=timestamp,
        finished_at=timestamp,
        duration_ms=30,
        command_text="python -m pytest -q",
        argv=["python", "-m", "pytest", "-q"],
        cwd=tmp_path,
        exit_code=0,
        command_kind="test",
        stdout=".\n",
        stderr="",
    )

    report = build_commit_message_report(
        changes=[
            CommitFileChange(path="src/agent_flight_recorder/reports.py", status_code=" M", category="modified"),
            CommitFileChange(path="tests/test_reports.py", status_code=" M", category="modified"),
        ],
        additions=22,
        deletions=10,
        commands=store.list_commands(session.id),
    )

    assert report.primary.type == "fix"
    assert report.primary.message == "fix(report): fix session reporting"
    assert "failure followed by successful verification" in report.primary.rationale
    assert "At least one recorded command failed" in report.warnings[0]

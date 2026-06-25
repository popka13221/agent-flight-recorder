"""Structured recorder data for JSON and MCP consumers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from agent_flight_recorder.commands import relativize_cwd
from agent_flight_recorder.repo import GitDiffStat, GitFileChange, list_file_changes, read_diff_stat
from agent_flight_recorder.reports import build_session_report
from agent_flight_recorder.risks import RiskFinding, analyze_risks, findings_from_snapshot_payload
from agent_flight_recorder.store import (
    CommandRecord,
    EventRecord,
    RecorderStore,
    SessionRecord,
    SnapshotRecord,
)


DEFAULT_EVENT_LIMIT = 10
DEFAULT_COMMAND_LIMIT = 20
MAX_COMMAND_LIMIT = 100
SnapshotSource = Literal["live", "snapshot"]


class SessionResolutionError(LookupError):
    """Raised when a requested session id does not exist."""


def format_timestamp(value: datetime | None) -> str:
    """Render timestamps in compact UTC form."""

    if value is None:
        return "-"

    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_target_session(
    store: RecorderStore,
    session_id: int | None = None,
) -> SessionRecord | None:
    """Resolve a specific session id or fall back to active/latest session."""

    if session_id is None:
        return store.get_active_session() or store.get_latest_session()

    session = store.get_session(session_id)
    if session is None:
        raise SessionResolutionError(f"session {session_id} was not found")

    return session


def build_current_session_payload(
    store: RecorderStore,
    *,
    event_limit: int = DEFAULT_EVENT_LIMIT,
) -> dict[str, object]:
    """Return the current or latest recorded session with recent timeline events."""

    session = resolve_target_session(store)
    payload: dict[str, object] = {
        "repo_root": str(store.repo_root),
        "store_path": str(store.db_path),
        "session": session_to_dict(session),
        "recent_events": [],
    }
    if session is None:
        payload["message"] = "No recorded sessions."
        return payload

    events = store.list_events(session.id)
    if event_limit > 0:
        payload["recent_events"] = [event_to_dict(event) for event in events[-event_limit:]]

    return payload


def build_changed_files_payload(
    store: RecorderStore,
    *,
    source: SnapshotSource = "live",
    session_id: int | None = None,
) -> dict[str, object]:
    """Return changed file details from the live worktree or latest snapshot."""

    source = normalize_snapshot_source(source)
    if source == "live":
        changes = list_file_changes(store.repo_root)
        diff_stat = read_diff_stat(store.repo_root)
        risks = analyze_risks(store.repo_root, changes, diff_stat)
        return {
            "repo_root": str(store.repo_root),
            "source": "live",
            "session": session_to_dict(resolve_target_session(store, session_id)),
            "diff": diff_stat_to_dict(diff_stat),
            "files": [change_to_dict(change) for change in changes],
            "risk_count": len(risks),
        }

    session = resolve_target_session(store, session_id)
    snapshot = store.get_latest_snapshot(session.id) if session is not None else None
    payload: dict[str, object] = {
        "repo_root": str(store.repo_root),
        "source": "snapshot",
        "session": session_to_dict(session),
        "snapshot": snapshot_to_dict(snapshot),
        "files": snapshot_files(snapshot),
        "risk_count": len(snapshot_risks(snapshot)),
    }
    if session is None:
        payload["message"] = "No recorded sessions."
    elif snapshot is None:
        payload["message"] = f"Session {session.id} has no recorded snapshot."

    return payload


def build_command_history_payload(
    store: RecorderStore,
    *,
    session_id: int | None = None,
    limit: int = DEFAULT_COMMAND_LIMIT,
    failed_only: bool = False,
) -> dict[str, object]:
    """Return recent commands for the selected session."""

    session = resolve_target_session(store, session_id)
    payload: dict[str, object] = {
        "repo_root": str(store.repo_root),
        "session": session_to_dict(session),
        "commands": [],
        "failed_only": failed_only,
    }
    if session is None:
        payload["message"] = "No recorded sessions."
        return payload

    bounded_limit = max(1, min(limit, MAX_COMMAND_LIMIT))
    commands = (
        store.list_failed_commands(session.id, limit=bounded_limit)
        if failed_only
        else store.list_commands(session.id, limit=bounded_limit)
    )
    payload["commands"] = [
        command_to_dict(command, repo_root=store.repo_root, include_output=True) for command in commands
    ]
    payload["total_commands"] = store.count_commands(session.id)
    payload["returned_commands"] = len(commands)
    return payload


def build_risk_report_payload(
    store: RecorderStore,
    *,
    source: SnapshotSource = "live",
    session_id: int | None = None,
) -> dict[str, object]:
    """Return risk findings from the live worktree or the latest snapshot."""

    source = normalize_snapshot_source(source)
    if source == "live":
        changes = list_file_changes(store.repo_root)
        diff_stat = read_diff_stat(store.repo_root)
        risks = analyze_risks(store.repo_root, changes, diff_stat)
        return {
            "repo_root": str(store.repo_root),
            "source": "live",
            "session": session_to_dict(resolve_target_session(store, session_id)),
            "diff": diff_stat_to_dict(diff_stat),
            "risks": [risk.to_dict() for risk in risks],
        }

    session = resolve_target_session(store, session_id)
    snapshot = store.get_latest_snapshot(session.id) if session is not None else None
    risks = snapshot_risks(snapshot)
    payload: dict[str, object] = {
        "repo_root": str(store.repo_root),
        "source": "snapshot",
        "session": session_to_dict(session),
        "snapshot": snapshot_to_dict(snapshot),
        "risks": [risk.to_dict() for risk in risks],
    }
    if session is None:
        payload["message"] = "No recorded sessions."
    elif snapshot is None:
        payload["message"] = f"Session {session.id} has no recorded snapshot."

    return payload


def build_session_summary_payload(
    store: RecorderStore,
    *,
    session_id: int | None = None,
) -> dict[str, object]:
    """Return a compact session summary with checks, commands, and risks."""

    session = resolve_target_session(store, session_id)
    payload: dict[str, object] = {
        "repo_root": str(store.repo_root),
        "store_path": str(store.db_path),
        "session": session_to_dict(session),
    }
    if session is None:
        payload["message"] = "No recorded sessions."
        return payload

    report = build_session_report(store, session)
    payload["latest_snapshot"] = snapshot_to_dict(report.latest_snapshot)
    payload["command_count"] = len(report.commands)
    payload["failed_command_count"] = len(report.failed_commands)
    payload["latest_command"] = (
        command_to_dict(report.commands[0], repo_root=store.repo_root, include_output=False)
        if report.commands
        else None
    )
    payload["risks"] = [risk.to_dict() for risk in report.risks]
    payload["next_checks"] = report.next_checks
    return payload


def session_to_dict(session: SessionRecord | None) -> dict[str, object] | None:
    """Convert one session record into a stable JSON-friendly payload."""

    if session is None:
        return None

    return {
        "id": session.id,
        "status": session.status,
        "repo_root": str(session.repo_root),
        "started_at": format_timestamp(session.started_at),
        "stopped_at": format_timestamp(session.stopped_at),
    }


def event_to_dict(event: EventRecord) -> dict[str, object]:
    """Convert one timeline event into a stable JSON-friendly payload."""

    return {
        "id": event.id,
        "session_id": event.session_id,
        "event_type": event.event_type,
        "created_at": format_timestamp(event.created_at),
        "detail": event.detail,
    }


def command_to_dict(
    command: CommandRecord,
    *,
    repo_root: Path,
    include_output: bool,
) -> dict[str, object]:
    """Convert one command record into a stable JSON-friendly payload."""

    payload = {
        "id": command.id,
        "session_id": command.session_id,
        "started_at": format_timestamp(command.started_at),
        "finished_at": format_timestamp(command.finished_at),
        "duration_ms": command.duration_ms,
        "command": command.command_text,
        "argv": command.argv,
        "cwd": relativize_cwd(command.cwd, repo_root),
        "exit_code": command.exit_code,
        "kind": command.command_kind,
    }
    if include_output:
        payload["stdout"] = command.stdout
        payload["stderr"] = command.stderr

    return payload


def snapshot_to_dict(snapshot: SnapshotRecord | None) -> dict[str, object] | None:
    """Convert one snapshot record into a stable JSON-friendly payload."""

    if snapshot is None:
        return None

    return {
        "id": snapshot.id,
        "session_id": snapshot.session_id,
        "created_at": format_timestamp(snapshot.created_at),
        "files_changed": snapshot.files_changed,
        "additions": snapshot.additions,
        "deletions": snapshot.deletions,
    }


def diff_stat_to_dict(diff_stat: GitDiffStat) -> dict[str, object]:
    """Convert a diff stat object into a stable JSON-friendly payload."""

    return {
        "files_changed": diff_stat.files_changed,
        "additions": diff_stat.additions,
        "deletions": diff_stat.deletions,
    }


def change_to_dict(change: GitFileChange) -> dict[str, object]:
    """Convert one git change entry into a stable JSON-friendly payload."""

    return {
        "path": change.path,
        "status": change.status_code,
        "category": change.category,
    }


def snapshot_files(snapshot: SnapshotRecord | None) -> list[dict[str, object]]:
    """Read changed-file data from a stored snapshot payload."""

    if snapshot is None:
        return []

    raw_files = snapshot.payload.get("files")
    if not isinstance(raw_files, list):
        return []

    files: list[dict[str, object]] = []
    for item in raw_files:
        if not isinstance(item, dict):
            continue
        files.append(
            {
                "path": str(item.get("path", "")),
                "status": str(item.get("status", "")),
                "category": str(item.get("category", "")),
            }
        )
    return files


def snapshot_risks(snapshot: SnapshotRecord | None) -> list[RiskFinding]:
    """Read risk findings from a stored snapshot payload."""

    if snapshot is None:
        return []

    return findings_from_snapshot_payload(snapshot.payload)


def normalize_snapshot_source(source: str) -> SnapshotSource:
    """Validate live-versus-snapshot source selectors."""

    if source not in {"live", "snapshot"}:
        raise ValueError("source must be 'live' or 'snapshot'")

    return source

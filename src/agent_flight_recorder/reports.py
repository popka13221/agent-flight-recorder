"""Session report builders and renderers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from agent_flight_recorder.commands import relativize_cwd
from agent_flight_recorder.store import CommandRecord, RecorderStore, SessionRecord, SnapshotRecord


@dataclass(frozen=True)
class SessionReport:
    """Aggregated recorder data for one session report."""

    session: SessionRecord
    latest_snapshot: SnapshotRecord | None
    commands: list[CommandRecord]
    failed_commands: list[CommandRecord]
    next_checks: list[str]


def build_session_report(store: RecorderStore, session: SessionRecord) -> SessionReport:
    """Read the latest reportable state for a session."""

    commands = store.list_commands(session.id)
    failed_commands = [command for command in commands if command.exit_code != 0]
    latest_snapshot = store.get_latest_snapshot(session.id)

    return SessionReport(
        session=session,
        latest_snapshot=latest_snapshot,
        commands=commands,
        failed_commands=failed_commands,
        next_checks=suggest_next_checks(
            latest_snapshot=latest_snapshot,
            commands=commands,
            failed_commands=failed_commands,
        ),
    )


def suggest_next_checks(
    *,
    latest_snapshot: SnapshotRecord | None,
    commands: list[CommandRecord],
    failed_commands: list[CommandRecord],
) -> list[str]:
    """Suggest useful next verification steps from recorded evidence."""

    suggestions: list[str] = []
    if latest_snapshot is None:
        suggestions.append("Run `afr snapshot` to capture the current worktree state.")

    if not commands:
        suggestions.append("Run tests or build checks through `afr run`.")
    elif failed_commands:
        suggestions.append("Investigate failed commands before committing or pushing.")

    if commands and not has_test_or_build_evidence(commands):
        suggestions.append("Record at least one test or build command before handoff.")

    if not suggestions:
        suggestions.append("Review the diff and commit the completed work.")

    return suggestions


def has_test_or_build_evidence(commands: list[CommandRecord]) -> bool:
    """Return whether commands include test/build/check evidence."""

    evidence_kinds = {"test", "build", "check"}
    return any(command.command_kind in evidence_kinds and command.exit_code == 0 for command in commands)


def render_text_report(report: SessionReport, *, repo_root: Path) -> str:
    """Render a report for terminal output."""

    lines = [
        f"Session {report.session.id} report",
        f"Status: {report.session.status}",
        f"Repo: {report.session.repo_root}",
        f"Started: {format_timestamp(report.session.started_at)}",
        f"Stopped: {format_timestamp(report.session.stopped_at)}",
        "",
        "Snapshot:",
        format_snapshot(report.latest_snapshot),
        "",
        "Commands:",
        f"  Total: {len(report.commands)}",
        f"  Failed: {len(report.failed_commands)}",
    ]
    for command in report.commands[:5]:
        lines.append(format_command_line(command, repo_root=repo_root, markdown=False))

    lines.extend(["", "Next checks:"])
    lines.extend(f"  - {suggestion}" for suggestion in report.next_checks)
    return "\n".join(lines) + "\n"


def render_markdown_report(report: SessionReport, *, repo_root: Path) -> str:
    """Render a Markdown session report."""

    lines = [
        f"# AgentFlightRecorder Session {report.session.id}",
        "",
        f"- Status: `{report.session.status}`",
        f"- Repo: `{report.session.repo_root}`",
        f"- Started: `{format_timestamp(report.session.started_at)}`",
        f"- Stopped: `{format_timestamp(report.session.stopped_at)}`",
        "",
        "## Snapshot",
        "",
        format_snapshot(report.latest_snapshot, markdown=True),
        "",
        "## Commands",
        "",
        f"- Total: `{len(report.commands)}`",
        f"- Failed: `{len(report.failed_commands)}`",
    ]
    for command in report.commands[:10]:
        lines.append(format_command_line(command, repo_root=repo_root, markdown=True))

    lines.extend(["", "## Next Checks", ""])
    lines.extend(f"- {suggestion}" for suggestion in report.next_checks)
    return "\n".join(lines) + "\n"


def render_json_report(report: SessionReport, *, repo_root: Path) -> str:
    """Render a machine-readable JSON session report."""

    payload = {
        "session": {
            "id": report.session.id,
            "status": report.session.status,
            "repo_root": str(report.session.repo_root),
            "started_at": format_timestamp(report.session.started_at),
            "stopped_at": format_timestamp(report.session.stopped_at),
        },
        "snapshot": snapshot_to_dict(report.latest_snapshot),
        "commands": [
            {
                "id": command.id,
                "command": command.command_text,
                "kind": command.command_kind,
                "exit_code": command.exit_code,
                "duration_ms": command.duration_ms,
                "cwd": relativize_cwd(command.cwd, repo_root),
            }
            for command in report.commands
        ],
        "failed_commands": [command.id for command in report.failed_commands],
        "next_checks": report.next_checks,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def format_snapshot(snapshot: SnapshotRecord | None, *, markdown: bool = False) -> str:
    """Render latest snapshot statistics."""

    if snapshot is None:
        return "- No snapshot recorded." if markdown else "  No snapshot recorded."

    prefix = "- " if markdown else "  "
    return (
        f"{prefix}Snapshot {snapshot.id}: {snapshot.files_changed} files changed, "
        f"+{snapshot.additions}/-{snapshot.deletions}"
    )


def format_command_line(command: CommandRecord, *, repo_root: Path, markdown: bool) -> str:
    """Render one command summary line."""

    cwd = relativize_cwd(command.cwd, repo_root)
    line = (
        f"{command.command_kind} exit {command.exit_code} "
        f"({command.duration_ms} ms, cwd={cwd}): {command.command_text}"
    )
    return f"- `{line}`" if markdown else f"  {line}"


def snapshot_to_dict(snapshot: SnapshotRecord | None) -> dict[str, object] | None:
    """Convert a snapshot to a JSON-friendly payload."""

    if snapshot is None:
        return None

    return {
        "id": snapshot.id,
        "created_at": format_timestamp(snapshot.created_at),
        "files_changed": snapshot.files_changed,
        "additions": snapshot.additions,
        "deletions": snapshot.deletions,
        "payload": snapshot.payload,
    }


def format_timestamp(value: datetime | None) -> str:
    """Render timestamps in compact UTC form."""

    if value is None:
        return "-"

    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

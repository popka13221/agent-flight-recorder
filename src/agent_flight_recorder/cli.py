"""Command line interface for AgentFlightRecorder."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
import sys

from agent_flight_recorder import __version__
from agent_flight_recorder.commands import (
    InvalidCommandError,
    execute_command,
    normalize_command_args,
    relativize_cwd,
)
from agent_flight_recorder.repo import (
    GitDiffStat,
    GitFileChange,
    RepoResolutionError,
    list_file_changes,
    read_diff_stat,
    resolve_repo_root,
)
from agent_flight_recorder.reports import (
    build_session_report,
    render_json_report,
    render_markdown_report,
    render_text_report,
)
from agent_flight_recorder.store import (
    ActiveSessionError,
    CommandRecord,
    NoActiveSessionError,
    RecorderStore,
    SessionRecord,
)


COMMAND_DESCRIPTIONS = {
    "start": "start a new recording session",
    "current": "show the active recording session",
    "stop": "stop the active recording session",
    "status": "show repository and session status",
    "snapshot": "record the current git worktree state",
    "timeline": "show recorded session events",
    "run": "run a command and record its result",
    "report": "write a session report",
    "commit-msg": "suggest a commit message for the current diff",
}

IMPLEMENTED_COMMANDS = {
    "start",
    "current",
    "stop",
    "status",
    "snapshot",
    "timeline",
    "run",
    "report",
}


def format_timestamp(value: datetime | None) -> str:
    """Render timestamps using a compact UTC representation."""

    if value is None:
        return "-"

    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def write_session_summary(prefix: str, session: SessionRecord, store_path: Path) -> None:
    """Print a compact session summary for human-oriented CLI output."""

    print(f"{prefix} session {session.id}.")
    print(f"Repo: {session.repo_root}")
    print(f"Started: {format_timestamp(session.started_at)}")
    if session.stopped_at is not None:
        print(f"Stopped: {format_timestamp(session.stopped_at)}")
    print(f"Store: {store_path}")


def load_store() -> RecorderStore:
    """Resolve the current repository and open its recorder store."""

    repo_root = resolve_repo_root()
    return RecorderStore.open_for_repo(repo_root)


def load_repo_context() -> tuple[Path, RecorderStore]:
    """Resolve the current repository and store together."""

    repo_root = resolve_repo_root()
    return repo_root, RecorderStore.open_for_repo(repo_root)


def run_start() -> int:
    store = load_store()
    session = store.start_session()
    write_session_summary("Started", session, store.db_path)
    return 0


def run_current() -> int:
    store = load_store()
    session = store.get_active_session()
    if session is None:
        print("afr: no active session", file=sys.stderr)
        return 1

    write_session_summary("Active", session, store.db_path)
    return 0


def run_stop() -> int:
    store = load_store()
    session = store.stop_active_session()
    write_session_summary("Stopped", session, store.db_path)
    return 0


def run_status() -> int:
    repo_root, store = load_repo_context()
    session = store.get_active_session()
    changes = list_file_changes(repo_root)
    diff_stat = read_diff_stat(repo_root)
    latest_snapshot = store.get_latest_snapshot(session.id) if session else None
    command_count = store.count_commands(session.id) if session else 0
    latest_command = store.get_latest_command(session.id) if session else None
    failed_commands = store.list_failed_commands(session.id, limit=3) if session else []

    print(f"Repo: {repo_root}")
    print(f"Active session: {session.id if session else '-'}")
    print(f"Files changed: {len(changes)}")
    print(f"Tracked diff: +{diff_stat.additions}/-{diff_stat.deletions}")
    print(f"Latest snapshot: {latest_snapshot.id if latest_snapshot else '-'}")
    print(f"Commands recorded: {command_count}")
    print(f"Latest command: {format_command_summary(latest_command, repo_root) if latest_command else '-'}")
    if changes:
        print()
        print("Changes:")
        for change in changes:
            print(f"  {change.status_code}  {change.category:<10} {change.path}")
    if failed_commands:
        print()
        print("Recent failed commands:")
        for command in failed_commands:
            relative_cwd = relativize_cwd(command.cwd, repo_root)
            print(
                f"  exit {command.exit_code:<3} {command.command_kind:<7} {relative_cwd:<10} "
                f"{command.command_text}"
            )

    return 0


def run_snapshot() -> int:
    repo_root, store = load_repo_context()
    session = store.get_active_session()
    if session is None:
        print("afr: no active session", file=sys.stderr)
        return 1

    changes = list_file_changes(repo_root)
    diff_stat = read_diff_stat(repo_root)
    snapshot = store.record_snapshot(
        session_id=session.id,
        files_changed=len(changes),
        additions=diff_stat.additions,
        deletions=diff_stat.deletions,
        payload=build_snapshot_payload(changes, diff_stat),
    )

    print(f"Recorded snapshot {snapshot.id} for session {session.id}.")
    print(f"Files changed: {snapshot.files_changed}")
    print(f"Tracked diff: +{snapshot.additions}/-{snapshot.deletions}")
    print(f"Store: {store.db_path}")
    return 0


def run_timeline(session_id: int | None) -> int:
    store = load_store()
    session = store.get_session(session_id) if session_id is not None else None
    if session is None and session_id is not None:
        print(f"afr: session {session_id} was not found", file=sys.stderr)
        return 1

    if session is None:
        session = store.get_active_session() or store.get_latest_session()
    if session is None:
        print("afr: no recorded sessions", file=sys.stderr)
        return 1

    print(f"Timeline for session {session.id} ({session.status})")
    for event in store.list_events(session.id):
        print(f"{format_timestamp(event.created_at)}  {event.event_type}  {event.detail}")

    return 0


def run_command(command_args: Sequence[str]) -> int:
    argv = normalize_command_args(command_args)
    repo_root, store = load_repo_context()
    session = store.get_active_session()
    if session is None:
        print("afr: no active session", file=sys.stderr)
        return 1

    execution = execute_command(argv, cwd=Path.cwd())
    record = store.record_command(
        session_id=session.id,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        duration_ms=execution.duration_ms,
        command_text=execution.command_text,
        argv=execution.argv,
        cwd=execution.cwd,
        exit_code=execution.exit_code,
        command_kind=execution.command_kind,
        stdout=execution.stdout,
        stderr=execution.stderr,
    )

    print()
    print(f"Recorded command {record.id} for session {session.id}.")
    print(f"Kind: {record.command_kind}")
    print(f"Exit: {record.exit_code}")
    print(f"Duration: {record.duration_ms} ms")
    print(f"Cwd: {relativize_cwd(record.cwd, repo_root)}")
    return execution.exit_code


def run_report(session_id: int | None, output_format: str) -> int:
    repo_root, store = load_repo_context()
    session = store.get_session(session_id) if session_id is not None else None
    if session is None and session_id is not None:
        print(f"afr: session {session_id} was not found", file=sys.stderr)
        return 1

    if session is None:
        session = store.get_active_session() or store.get_latest_session()
    if session is None:
        print("afr: no recorded sessions", file=sys.stderr)
        return 1

    report = build_session_report(store, session)
    if output_format == "markdown":
        print(render_markdown_report(report, repo_root=repo_root), end="")
    elif output_format == "json":
        print(render_json_report(report, repo_root=repo_root), end="")
    else:
        print(render_text_report(report, repo_root=repo_root), end="")

    return 0


def run_planned_command(command: str) -> int:
    print(f"afr: command '{command}' is planned but not implemented yet", file=sys.stderr)
    return 2


def build_snapshot_payload(
    changes: list[GitFileChange],
    diff_stat: GitDiffStat,
) -> dict[str, object]:
    """Build a stable JSON payload for persisted git snapshots."""

    return {
        "files_changed": len(changes),
        "additions": diff_stat.additions,
        "deletions": diff_stat.deletions,
        "files": [
            {
                "path": change.path,
                "status": change.status_code,
                "category": change.category,
            }
            for change in changes
        ],
    }


def format_command_summary(command: CommandRecord, repo_root: Path) -> str:
    """Render one command in a compact status-friendly format."""

    relative_cwd = relativize_cwd(command.cwd, repo_root)
    return (
        f"{command.command_kind} exit {command.exit_code} "
        f"({command.duration_ms} ms, cwd={relative_cwd}): {command.command_text}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="afr",
        description="Local flight recorder for AI coding agent sessions.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"afr {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="command")
    for command, help_text in COMMAND_DESCRIPTIONS.items():
        command_parser = subparsers.add_parser(command, help=help_text)
        if command == "timeline":
            command_parser.add_argument(
                "--session",
                dest="session_id",
                type=int,
                help="show events for a specific session id",
            )
        if command == "run":
            command_parser.add_argument(
                "command_args",
                nargs=argparse.REMAINDER,
                help="command to execute; prefix with -- when the command uses flags",
            )
        if command == "report":
            command_parser.add_argument(
                "--session",
                dest="session_id",
                type=int,
                help="report on a specific session id",
            )
            format_group = command_parser.add_mutually_exclusive_group()
            format_group.add_argument(
                "--md",
                dest="output_format",
                action="store_const",
                const="markdown",
                help="render the report as Markdown",
            )
            format_group.add_argument(
                "--json",
                dest="output_format",
                action="store_const",
                const="json",
                help="render the report as JSON",
            )
            command_parser.set_defaults(output_format="text")
        command_parser.set_defaults(command=command)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command:
        try:
            if args.command == "start":
                return run_start()
            if args.command == "current":
                return run_current()
            if args.command == "stop":
                return run_stop()
            if args.command == "status":
                return run_status()
            if args.command == "snapshot":
                return run_snapshot()
            if args.command == "timeline":
                return run_timeline(args.session_id)
            if args.command == "run":
                return run_command(args.command_args)
            if args.command == "report":
                return run_report(args.session_id, args.output_format)
            if args.command not in IMPLEMENTED_COMMANDS:
                return run_planned_command(args.command)
        except RepoResolutionError as error:
            print(f"afr: {error}", file=sys.stderr)
            return 2
        except InvalidCommandError as error:
            print(f"afr: {error}", file=sys.stderr)
            return 2
        except ActiveSessionError as error:
            print(f"afr: session {error.session_id} is already active", file=sys.stderr)
            return 1
        except NoActiveSessionError as error:
            print(f"afr: {error}", file=sys.stderr)
            return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

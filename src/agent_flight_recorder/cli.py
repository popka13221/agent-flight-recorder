"""Command line interface for AgentFlightRecorder."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
import sys

from agent_flight_recorder import __version__
from agent_flight_recorder.repo import RepoResolutionError, resolve_repo_root
from agent_flight_recorder.store import ActiveSessionError, NoActiveSessionError, RecorderStore, SessionRecord


COMMAND_DESCRIPTIONS = {
    "start": "start a new recording session",
    "current": "show the active recording session",
    "stop": "stop the active recording session",
    "status": "show repository and session status",
    "timeline": "show recorded session events",
    "report": "write a session report",
    "commit-msg": "suggest a commit message for the current diff",
}

IMPLEMENTED_COMMANDS = {"start", "current", "stop", "timeline"}


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


def run_planned_command(command: str) -> int:
    print(f"afr: command '{command}' is planned but not implemented yet", file=sys.stderr)
    return 2


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
            if args.command == "timeline":
                return run_timeline(args.session_id)
            if args.command not in IMPLEMENTED_COMMANDS:
                return run_planned_command(args.command)
        except RepoResolutionError as error:
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

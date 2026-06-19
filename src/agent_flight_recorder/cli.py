"""Command line interface for AgentFlightRecorder."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from agent_flight_recorder import __version__


COMMAND_DESCRIPTIONS = {
    "start": "start a new recording session",
    "status": "show repository and session status",
    "timeline": "show recorded session events",
    "report": "write a session report",
    "commit-msg": "suggest a commit message for the current diff",
}


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
        command_parser.set_defaults(command=command)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command:
        parser.exit(2, f"afr: command '{args.command}' is planned but not implemented yet\n")

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# AgentFlightRecorder

AgentFlightRecorder is a local-first flight recorder for AI coding agent sessions.
It tracks what changed, which commands ran, what failed, and what should be checked
before a commit or pull request leaves the machine.

The goal is simple: when an AI coding agent edits a repository, developers should
be able to answer three questions quickly:

- What happened?
- Why is this diff risky?
- What evidence proves the change was checked?

## Planned Workflow

```bash
afr start
afr status
afr run "pytest"
afr timeline
afr report --md
afr commit-msg
```

The first versions focus on a small CLI that works without cloud services. Later
versions can add MCP support, richer risk analysis, and UI surfaces for reviewing
agent sessions.

## Current MVP

The repository currently ships the first CLI skeleton:

```bash
PYTHONPATH=src python -m agent_flight_recorder.cli --help
PYTHONPATH=src python -m agent_flight_recorder.cli --version
```

The planned commands are visible in help output and intentionally return a clear
"planned but not implemented yet" message until their backing storage and git
integration are added.

## Development

Run the smoke tests:

```bash
PYTHONPATH=src python -m pytest -q
```

## Principles

- Local-first: project code and session data stay on the developer machine by default.
- Tool-agnostic: usable with Codex, Claude Code, Cursor, terminal scripts, and manual work.
- Evidence-driven: reports should include commands, exit codes, changed files, and risks.
- Small commands: every feature should be scriptable and useful in CI or local hooks.

## Status

This repository is at the first implementation stage. The initial milestone is a
working Python CLI with session storage, git snapshots, command logging, and
Markdown reports.

## License

MIT license planned.

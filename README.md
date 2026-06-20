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
afr current
afr timeline
afr stop
```

The first versions focus on a small CLI that works without cloud services. Later
versions can add MCP support, richer risk analysis, and UI surfaces for reviewing
agent sessions.

## Current MVP

The repository currently ships a working local session recorder:

```bash
PYTHONPATH=src python -m agent_flight_recorder.cli --help
PYTHONPATH=src python -m agent_flight_recorder.cli start
PYTHONPATH=src python -m agent_flight_recorder.cli current
PYTHONPATH=src python -m agent_flight_recorder.cli timeline
PYTHONPATH=src python -m agent_flight_recorder.cli stop
```

Sessions are stored in a repository-local SQLite database at
`.afr/flight_recorder.db`. Today the recorder captures session lifecycle events;
git snapshots, command logging, and reports are the next layers on top.

Commands that have not reached implementation yet still return a clear
"planned but not implemented yet" message.

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

This repository now has the first usable recorder milestone: a Python CLI with
repository discovery, SQLite-backed session storage, and timeline output. The
next milestone is git snapshot capture and status summaries for active sessions.

## License

MIT

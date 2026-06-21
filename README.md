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
afr run -- python -m pytest -q
afr current
afr status
afr snapshot
afr timeline
afr report
afr report --md
afr report --json
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
PYTHONPATH=src python -m agent_flight_recorder.cli run -- python -m pytest -q
PYTHONPATH=src python -m agent_flight_recorder.cli current
PYTHONPATH=src python -m agent_flight_recorder.cli status
PYTHONPATH=src python -m agent_flight_recorder.cli snapshot
PYTHONPATH=src python -m agent_flight_recorder.cli timeline
PYTHONPATH=src python -m agent_flight_recorder.cli report
PYTHONPATH=src python -m agent_flight_recorder.cli report --md
PYTHONPATH=src python -m agent_flight_recorder.cli report --json
PYTHONPATH=src python -m agent_flight_recorder.cli stop
```

Sessions are stored in a repository-local SQLite database at
`.afr/flight_recorder.db`. The recorder captures session lifecycle events and
git worktree snapshots, including changed files and tracked diff statistics.
`afr run` executes commands inside the active session, stores exit code,
duration, stdout, stderr, and a coarse command kind, then surfaces recent
failures in `afr status` and the session timeline. It ignores its own `.afr/`
state so recorder data does not pollute reports.
`afr report` summarizes the session in terminal, Markdown, or JSON form with
latest snapshot data, command evidence, failed commands, and suggested next
checks.

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

This repository now has the first usable recorder milestones: a Python CLI with
repository discovery, SQLite-backed session storage, timeline output, worktree
status summaries, persisted git snapshots, and command logging through
`afr run`. It can now generate terminal, Markdown, and JSON session reports.
The next milestone is commit intelligence through `afr commit-msg`.

## License

MIT

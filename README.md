# AgentFlightRecorder

[![CI](https://github.com/popka13221/agent-flight-recorder/actions/workflows/ci.yml/badge.svg)](https://github.com/popka13221/agent-flight-recorder/actions/workflows/ci.yml)

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
afr commit-msg
afr commit-msg --json
afr ui
afr mcp
afr stop
```

The first versions focus on a small CLI that works without cloud services. Later
versions can add MCP support, richer risk analysis, and UI surfaces for reviewing
agent sessions.

## Current MVP

The repository currently ships a working local session recorder:

```bash
afr --help
afr start
afr run -- python -m pytest -q
afr current
afr status
afr snapshot
afr timeline
afr report
afr report --md
afr report --json
afr commit-msg
afr commit-msg --json
afr ui
afr mcp
afr stop
```

## Installation

PyPI publishing is still on the roadmap. Until then, install from GitHub or a
local checkout:

```bash
python -m pip install "git+https://github.com/popka13221/agent-flight-recorder.git"
afr --help
```

For local development:

```bash
git clone https://github.com/popka13221/agent-flight-recorder.git
cd agent-flight-recorder
python -m pip install -e ".[dev]"
afr --help
```

Sessions are stored in a repository-local SQLite database at
`.afr/flight_recorder.db`. The recorder captures session lifecycle events and
git worktree snapshots, including changed files and tracked diff statistics.
`afr run` executes commands inside the active session, stores exit code,
duration, stdout, stderr, and a coarse command kind, then surfaces recent
failures in `afr status` and the session timeline. It ignores its own `.afr/`
state so recorder data does not pollute reports.
The recorder also evaluates the worktree for review risks such as real `.env`
files, secret-like patterns, security-sensitive paths, large diffs, source
changes without nearby tests, and manifest changes that skipped an existing
lockfile update.
`afr report` summarizes the session in terminal, Markdown, or JSON form with
latest snapshot data, persisted risk findings, command evidence, failed
commands, and suggested next checks.
`afr commit-msg` inspects the current diff, combines it with recorded command
evidence when available, and suggests a conventional commit message plus a
changelog-ready bullet. JSON output is available for editor or hook
integrations.
`afr mcp` runs a read-only MCP server so coding agents can inspect the current
or latest recorder session, changed files, command history, risk findings, and
summary checks for the repository.
`afr ui` renders a compact terminal dashboard for the current or latest session
without adding a heavy TUI dependency.

Commands that have not reached implementation yet still return a clear
"planned but not implemented yet" message.

## Commit Message Workflow

Use `afr commit-msg` near the end of a session to generate a starting point for
your commit:

```bash
afr commit-msg
afr commit-msg --json
```

The first version is heuristic by design. It looks at changed file areas such as
`src/`, `tests/`, docs, and tooling files, then combines that with recorded
test/build/check outcomes to bias the suggestion toward `feat`, `fix`, `docs`,
`test`, `refactor`, or `chore`.

## Risk Review Workflow

Use the recorder's status and report surfaces before a handoff or push:

```bash
afr status
afr snapshot
afr report --md
```

`afr status` evaluates the live worktree and prints current risk findings.
`afr snapshot` persists those findings into the session record, and `afr report`
replays them later in terminal, Markdown, or JSON output.

## MCP Workflow

Use the MCP server when you want an AI client to read recorder state directly:

```bash
afr mcp
afr mcp --repo /absolute/path/to/repo
afr mcp --transport streamable-http
```

The initial server is intentionally read-only. It exposes focused tools for the
current session, changed files, command history, risk findings, and session
summary so agents can decide what to inspect or verify next.

## Terminal UI Workflow

Use the dependency-free terminal dashboard when you want a fast review surface:

```bash
afr ui
afr ui --session 1
```

The first UI pass focuses on a static session overview: snapshot totals, risk
findings, recent command evidence, failed command counts, and suggested next
checks.

## Development

Run the local checks before pushing:

```bash
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest -q
python -m build
```

GitHub Actions runs the same validation on pushes and pull requests, then
verifies that the built wheel exposes a working `afr` entrypoint. Version tags
named `v*` also produce release artifacts through the GitHub release workflow.
See `CONTRIBUTING.md` for the contributor workflow and release checklist.

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
It also suggests heuristic conventional commit messages and changelog snippets
through `afr commit-msg`. It now ships the first risk engine pass for local
review triage, plus a read-only MCP server for agent-facing repository session
inspection. Release readiness now includes CI, GitHub release packaging, local
install instructions, and a contributor workflow. It now includes a lightweight
terminal dashboard through `afr ui`. The next milestone is a local web UI or
demo recording for README.

## License

MIT

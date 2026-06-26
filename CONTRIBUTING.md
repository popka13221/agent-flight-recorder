# Contributing

AgentFlightRecorder is still early. The goal is to keep the project small,
scriptable, and useful for real local development workflows.

## Development Setup

```bash
git clone https://github.com/popka13221/agent-flight-recorder.git
cd agent-flight-recorder
python -m pip install -e ".[dev]"
```

The project requires Python 3.11 or newer.

## Local Checks

Run the same checks that CI runs before opening a pull request:

```bash
python -m ruff check .
python -m pytest -q
python -m build
```

The build step is important because AgentFlightRecorder is meant to work as an
installed CLI, not only from `PYTHONPATH=src`.

## Workflow

1. Create a focused change.
2. Add or update tests when behavior changes.
3. Run the local checks.
4. Use `afr snapshot`, `afr report`, or `afr commit-msg` if they help review the work.
5. Open a pull request with a conventional commit style title when possible.

## Release Flow

GitHub Actions provides two repository workflows:

- `CI` runs on pushes to `main` and on pull requests across Python 3.11, 3.12,
  and 3.13.
- `Release` runs when a tag matching `v*` is pushed and attaches the built
  wheel and source distribution to a GitHub release.

PyPI publishing is not automated yet. That remains a separate roadmap item.

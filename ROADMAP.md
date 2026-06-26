# Roadmap

AgentFlightRecorder should grow through small, useful daily increments. Each day
should normally produce three to five meaningful commits and end with a push to
GitHub.

## Daily Development Loop

1. Inspect repository state with `git status`, recent commits, and this roadmap.
2. Pick one focused work block for the day.
3. Split the block into small commits: docs, feature, tests, fixes, and examples.
4. Run the available checks before pushing.
5. Push to `main` while the project is young; move to branches and PRs once the
   project has external users or larger changes.

## Phase 1: Foundation

- [x] Create public GitHub repository.
- [x] Add project vision.
- [x] Add Python packaging metadata.
- [x] Add `afr` CLI entrypoint.
- [x] Add first smoke tests.
- [x] Add MIT license.

## Phase 2: Session Recorder MVP

- [x] Add SQLite-backed session store.
- [x] Implement `afr start`.
- [x] Implement `afr current`.
- [x] Implement `afr stop`.
- [x] Implement `afr timeline`.

## Phase 3: Git Snapshot Engine

- [x] Parse `git status --porcelain`.
- [x] Capture changed files by status.
- [x] Capture diff statistics.
- [x] Store snapshots per session.
- [x] Show `afr status` summary.

## Phase 4: Command Runner

- [x] Implement `afr run`.
- [x] Store command, exit code, duration, stdout, and stderr.
- [x] Detect likely test/build commands.
- [x] Surface failed commands in reports.

## Phase 5: Reports

- [x] Implement terminal report output.
- [x] Implement `afr report --md`.
- [x] Implement `afr report --json`.
- [x] Add suggested next checks.

## Phase 6: Commit Intelligence

- [x] Implement heuristic `afr commit-msg`.
- [x] Add Conventional Commit style suggestions.
- [x] Generate changelog snippets.
- [ ] Add optional AI provider integration later.

## Phase 7: Risk Engine

- [x] Detect secrets and `.env` files.
- [x] Flag security-sensitive paths.
- [x] Flag large diffs.
- [x] Flag source changes without nearby tests.
- [x] Flag package file changes without lockfile updates.

## Phase 8: MCP Server

- [x] Expose current session to agents.
- [x] Expose changed files and command history.
- [x] Expose risk report.
- [x] Expose session summary.

## Phase 9: Review UI

- [ ] Add terminal UI.
- [ ] Add local web UI.
- [ ] Add demo recording for README.

## Phase 10: Release

- [ ] Publish to PyPI.
- [x] Add GitHub Actions CI.
- [x] Add GitHub release workflow.
- [x] Add install examples.
- [x] Add contributing guide.

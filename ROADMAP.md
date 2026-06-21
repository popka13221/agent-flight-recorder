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

- [ ] Implement terminal report output.
- [ ] Implement `afr report --md`.
- [ ] Implement `afr report --json`.
- [ ] Add suggested next checks.

## Phase 6: Commit Intelligence

- [ ] Implement heuristic `afr commit-msg`.
- [ ] Add Conventional Commit style suggestions.
- [ ] Generate changelog snippets.
- [ ] Add optional AI provider integration later.

## Phase 7: Risk Engine

- [ ] Detect secrets and `.env` files.
- [ ] Flag security-sensitive paths.
- [ ] Flag large diffs.
- [ ] Flag source changes without nearby tests.
- [ ] Flag package file changes without lockfile updates.

## Phase 8: MCP Server

- [ ] Expose current session to agents.
- [ ] Expose changed files and command history.
- [ ] Expose risk report.
- [ ] Expose session summary.

## Phase 9: Review UI

- [ ] Add terminal UI.
- [ ] Add local web UI.
- [ ] Add demo recording for README.

## Phase 10: Release

- [ ] Publish to PyPI.
- [ ] Add GitHub Actions CI.
- [ ] Add GitHub release workflow.
- [ ] Add install examples.
- [ ] Add contributing guide.

"""SQLite-backed session storage for AgentFlightRecorder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


DEFAULT_DATA_DIRNAME = ".afr"
DEFAULT_DB_FILENAME = "flight_recorder.db"


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp without microseconds."""

    return datetime.now(timezone.utc).replace(microsecond=0)


def format_timestamp(value: datetime) -> str:
    """Persist timestamps using ISO 8601 with explicit UTC offset."""

    return value.isoformat()


def parse_timestamp(value: str | None) -> datetime | None:
    """Parse ISO 8601 timestamps read from SQLite."""

    if value is None:
        return None

    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class SessionRecord:
    """A persisted recorder session."""

    id: int
    repo_root: Path
    status: str
    started_at: datetime
    stopped_at: datetime | None


@dataclass(frozen=True)
class EventRecord:
    """A persisted session event."""

    id: int
    session_id: int
    event_type: str
    created_at: datetime
    detail: str


@dataclass(frozen=True)
class SnapshotRecord:
    """A persisted git worktree snapshot."""

    id: int
    session_id: int
    created_at: datetime
    files_changed: int
    additions: int
    deletions: int
    payload: dict[str, object]


@dataclass(frozen=True)
class CommandRecord:
    """A persisted command execution captured during a session."""

    id: int
    session_id: int
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    command_text: str
    argv: list[str]
    cwd: Path
    exit_code: int
    command_kind: str
    stdout: str
    stderr: str


class ActiveSessionError(RuntimeError):
    """Raised when starting a session while another one is active."""

    def __init__(self, session_id: int) -> None:
        super().__init__(f"session {session_id} is already active")
        self.session_id = session_id


class NoActiveSessionError(RuntimeError):
    """Raised when a command requires an active session but none exists."""


class RecorderStore:
    """Manage session and event persistence for a single repository."""

    def __init__(self, repo_root: Path, db_path: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.db_path = db_path.resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @classmethod
    def open_for_repo(
        cls,
        repo_root: Path,
        *,
        data_dirname: str = DEFAULT_DATA_DIRNAME,
        db_filename: str = DEFAULT_DB_FILENAME,
    ) -> "RecorderStore":
        """Create or open the default SQLite store for ``repo_root``."""

        return cls(
            repo_root=repo_root,
            db_path=repo_root / data_dirname / db_filename,
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_root TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('active', 'stopped')),
                    started_at TEXT NOT NULL,
                    stopped_at TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    files_changed INTEGER NOT NULL,
                    additions INTEGER NOT NULL,
                    deletions INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    command_text TEXT NOT NULL,
                    argv_json TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    exit_code INTEGER NOT NULL,
                    command_kind TEXT NOT NULL,
                    stdout_text TEXT NOT NULL,
                    stderr_text TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_repo_started_at
                    ON sessions(repo_root, started_at DESC);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_repo_active
                    ON sessions(repo_root) WHERE status = 'active';

                CREATE INDEX IF NOT EXISTS idx_events_session_created_at
                    ON events(session_id, created_at, id);

                CREATE INDEX IF NOT EXISTS idx_snapshots_session_created_at
                    ON snapshots(session_id, created_at DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_commands_session_started_at
                    ON commands(session_id, started_at DESC, id DESC);
                """
            )

    def start_session(self) -> SessionRecord:
        """Create a new active session and emit its lifecycle event."""

        active_session = self.get_active_session()
        if active_session is not None:
            raise ActiveSessionError(active_session.id)

        timestamp = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO sessions(repo_root, status, started_at, stopped_at)
                VALUES (?, 'active', ?, NULL)
                """,
                (str(self.repo_root), format_timestamp(timestamp)),
            )
            session_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO events(session_id, event_type, created_at, detail)
                VALUES (?, 'session_started', ?, ?)
                """,
                (session_id, format_timestamp(timestamp), "Session started"),
            )

        session = self.get_session(session_id)
        assert session is not None
        return session

    def get_session(self, session_id: int) -> SessionRecord | None:
        """Return one session by id."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, repo_root, status, started_at, stopped_at
                FROM sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()

        return self._row_to_session(row) if row else None

    def get_active_session(self) -> SessionRecord | None:
        """Return the currently active session for this repository."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, repo_root, status, started_at, stopped_at
                FROM sessions
                WHERE repo_root = ? AND status = 'active'
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (str(self.repo_root),),
            ).fetchone()

        return self._row_to_session(row) if row else None

    def get_latest_session(self) -> SessionRecord | None:
        """Return the newest session for this repository."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, repo_root, status, started_at, stopped_at
                FROM sessions
                WHERE repo_root = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (str(self.repo_root),),
            ).fetchone()

        return self._row_to_session(row) if row else None

    def stop_active_session(self) -> SessionRecord:
        """Stop the active session and emit its lifecycle event."""

        active_session = self.get_active_session()
        if active_session is None:
            raise NoActiveSessionError("no active session")

        timestamp = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET status = 'stopped', stopped_at = ?
                WHERE id = ?
                """,
                (format_timestamp(timestamp), active_session.id),
            )
            connection.execute(
                """
                INSERT INTO events(session_id, event_type, created_at, detail)
                VALUES (?, 'session_stopped', ?, ?)
                """,
                (active_session.id, format_timestamp(timestamp), "Session stopped"),
            )

        session = self.get_session(active_session.id)
        assert session is not None
        return session

    def list_events(self, session_id: int) -> list[EventRecord]:
        """Return all recorded events for one session in chronological order."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, event_type, created_at, detail
                FROM events
                WHERE session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,),
            ).fetchall()

        return [self._row_to_event(row) for row in rows]

    def record_snapshot(
        self,
        *,
        session_id: int,
        files_changed: int,
        additions: int,
        deletions: int,
        payload: dict[str, object],
    ) -> SnapshotRecord:
        """Persist a git snapshot and emit an event for the session timeline."""

        timestamp = utc_now()
        payload_json = json.dumps(payload, sort_keys=True)
        detail = f"{files_changed} files changed, +{additions}/-{deletions}"
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO snapshots(
                    session_id,
                    created_at,
                    files_changed,
                    additions,
                    deletions,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    format_timestamp(timestamp),
                    files_changed,
                    additions,
                    deletions,
                    payload_json,
                ),
            )
            snapshot_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO events(session_id, event_type, created_at, detail)
                VALUES (?, 'snapshot_recorded', ?, ?)
                """,
                (session_id, format_timestamp(timestamp), detail),
            )

        snapshot = self.get_snapshot(snapshot_id)
        assert snapshot is not None
        return snapshot

    def get_snapshot(self, snapshot_id: int) -> SnapshotRecord | None:
        """Return one snapshot by id."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, session_id, created_at, files_changed, additions, deletions, payload_json
                FROM snapshots
                WHERE id = ?
                """,
                (snapshot_id,),
            ).fetchone()

        return self._row_to_snapshot(row) if row else None

    def get_latest_snapshot(self, session_id: int) -> SnapshotRecord | None:
        """Return the newest snapshot for a session."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, session_id, created_at, files_changed, additions, deletions, payload_json
                FROM snapshots
                WHERE session_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()

        return self._row_to_snapshot(row) if row else None

    def list_snapshots(self, session_id: int) -> list[SnapshotRecord]:
        """Return snapshots for a session from newest to oldest."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, created_at, files_changed, additions, deletions, payload_json
                FROM snapshots
                WHERE session_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (session_id,),
            ).fetchall()

        return [self._row_to_snapshot(row) for row in rows]

    def record_command(
        self,
        *,
        session_id: int,
        started_at: datetime,
        finished_at: datetime,
        duration_ms: int,
        command_text: str,
        argv: list[str],
        cwd: Path,
        exit_code: int,
        command_kind: str,
        stdout: str,
        stderr: str,
    ) -> CommandRecord:
        """Persist a command execution and emit a timeline event."""

        detail = build_command_detail(
            command_text=command_text,
            command_kind=command_kind,
            exit_code=exit_code,
            duration_ms=duration_ms,
        )
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO commands(
                    session_id,
                    started_at,
                    finished_at,
                    duration_ms,
                    command_text,
                    argv_json,
                    cwd,
                    exit_code,
                    command_kind,
                    stdout_text,
                    stderr_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    format_timestamp(started_at),
                    format_timestamp(finished_at),
                    duration_ms,
                    command_text,
                    json.dumps(argv),
                    str(cwd.resolve()),
                    exit_code,
                    command_kind,
                    stdout,
                    stderr,
                ),
            )
            command_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO events(session_id, event_type, created_at, detail)
                VALUES (?, ?, ?, ?)
                """,
                (
                    session_id,
                    "command_failed" if exit_code != 0 else "command_succeeded",
                    format_timestamp(finished_at),
                    detail,
                ),
            )

        command = self.get_command(command_id)
        assert command is not None
        return command

    def get_command(self, command_id: int) -> CommandRecord | None:
        """Return one recorded command by id."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    session_id,
                    started_at,
                    finished_at,
                    duration_ms,
                    command_text,
                    argv_json,
                    cwd,
                    exit_code,
                    command_kind,
                    stdout_text,
                    stderr_text
                FROM commands
                WHERE id = ?
                """,
                (command_id,),
            ).fetchone()

        return self._row_to_command(row) if row else None

    def get_latest_command(self, session_id: int) -> CommandRecord | None:
        """Return the newest recorded command for a session."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    session_id,
                    started_at,
                    finished_at,
                    duration_ms,
                    command_text,
                    argv_json,
                    cwd,
                    exit_code,
                    command_kind,
                    stdout_text,
                    stderr_text
                FROM commands
                WHERE session_id = ?
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()

        return self._row_to_command(row) if row else None

    def list_commands(self, session_id: int, *, limit: int | None = None) -> list[CommandRecord]:
        """Return recorded commands for a session from newest to oldest."""

        query = """
            SELECT
                id,
                session_id,
                started_at,
                finished_at,
                duration_ms,
                command_text,
                argv_json,
                cwd,
                exit_code,
                command_kind,
                stdout_text,
                stderr_text
            FROM commands
            WHERE session_id = ?
            ORDER BY started_at DESC, id DESC
        """
        parameters: tuple[object, ...]
        if limit is None:
            parameters = (session_id,)
        else:
            query += "\nLIMIT ?"
            parameters = (session_id, limit)

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()

        return [self._row_to_command(row) for row in rows]

    def list_failed_commands(self, session_id: int, *, limit: int = 5) -> list[CommandRecord]:
        """Return recent failed commands for a session."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    session_id,
                    started_at,
                    finished_at,
                    duration_ms,
                    command_text,
                    argv_json,
                    cwd,
                    exit_code,
                    command_kind,
                    stdout_text,
                    stderr_text
                FROM commands
                WHERE session_id = ? AND exit_code != 0
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        return [self._row_to_command(row) for row in rows]

    def count_commands(self, session_id: int) -> int:
        """Return how many commands have been recorded for a session."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS command_count
                FROM commands
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

        assert row is not None
        return int(row["command_count"])

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            id=int(row["id"]),
            repo_root=Path(row["repo_root"]),
            status=str(row["status"]),
            started_at=parse_timestamp(str(row["started_at"])) or utc_now(),
            stopped_at=parse_timestamp(row["stopped_at"]),
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> EventRecord:
        return EventRecord(
            id=int(row["id"]),
            session_id=int(row["session_id"]),
            event_type=str(row["event_type"]),
            created_at=parse_timestamp(str(row["created_at"])) or utc_now(),
            detail=str(row["detail"]),
        )

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row) -> SnapshotRecord:
        return SnapshotRecord(
            id=int(row["id"]),
            session_id=int(row["session_id"]),
            created_at=parse_timestamp(str(row["created_at"])) or utc_now(),
            files_changed=int(row["files_changed"]),
            additions=int(row["additions"]),
            deletions=int(row["deletions"]),
            payload=json.loads(str(row["payload_json"])),
        )

    @staticmethod
    def _row_to_command(row: sqlite3.Row) -> CommandRecord:
        return CommandRecord(
            id=int(row["id"]),
            session_id=int(row["session_id"]),
            started_at=parse_timestamp(str(row["started_at"])) or utc_now(),
            finished_at=parse_timestamp(str(row["finished_at"])) or utc_now(),
            duration_ms=int(row["duration_ms"]),
            command_text=str(row["command_text"]),
            argv=list(json.loads(str(row["argv_json"]))),
            cwd=Path(str(row["cwd"])),
            exit_code=int(row["exit_code"]),
            command_kind=str(row["command_kind"]),
            stdout=str(row["stdout_text"]),
            stderr=str(row["stderr_text"]),
        )


def build_command_detail(
    *,
    command_text: str,
    command_kind: str,
    exit_code: int,
    duration_ms: int,
) -> str:
    """Build a stable timeline detail string for one command execution."""

    label = command_kind if command_kind != "other" else "command"
    outcome = "failed" if exit_code != 0 else "passed"
    return f"{label} {outcome} (exit {exit_code}, {duration_ms} ms): {command_text}"

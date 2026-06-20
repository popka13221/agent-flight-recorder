"""SQLite-backed session storage for AgentFlightRecorder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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

                CREATE INDEX IF NOT EXISTS idx_sessions_repo_started_at
                    ON sessions(repo_root, started_at DESC);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_repo_active
                    ON sessions(repo_root) WHERE status = 'active';

                CREATE INDEX IF NOT EXISTS idx_events_session_created_at
                    ON events(session_id, created_at, id);
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

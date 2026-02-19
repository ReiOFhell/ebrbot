"""SQLite initialization and schema migration helpers for ebrbot."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable

DEFAULT_DB_FILENAME = "ebrbot.sqlite3"


PLAYERS_BASE_SQL = """
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL UNIQUE,
    display_name TEXT,
    created_at_utc TEXT NOT NULL
)
""".strip()

ANNALS_BASE_SQL = """
CREATE TABLE IF NOT EXISTS annals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    payload_json TEXT,
    timestamp_utc TEXT NOT NULL
)
""".strip()

FAILURE_LOGS_SQL = """
CREATE TABLE IF NOT EXISTS failure_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_name TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    user_id TEXT,
    hash_curto TEXT NOT NULL,
    error_text TEXT
)
""".strip()


def resolve_writable_db_path(preferred_path: str | os.PathLike[str] | None = None) -> Path:
    """Resolve a writable DB path, creating parent directories when needed."""

    candidates: list[Path] = []

    if preferred_path:
        candidates.append(Path(preferred_path).expanduser())

    env_path = os.getenv("EBRBOT_DB_PATH")
    if env_path:
        candidates.append(Path(env_path).expanduser())

    candidates.extend(
        [
            Path.cwd() / "data" / DEFAULT_DB_FILENAME,
            Path.cwd() / DEFAULT_DB_FILENAME,
        ]
    )

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            with open(candidate, "a", encoding="utf-8"):
                pass
            return candidate
        except OSError as exc:
            last_error = exc

    raise OSError("Could not resolve a writable database path") from last_error


def _fetch_existing_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def ensure_table_schema(
    conn: sqlite3.Connection,
    table_name: str,
    create_sql: str,
    required_columns: Iterable[tuple[str, str]],
) -> None:
    """Create table (if absent) and add missing columns without data loss."""

    conn.execute(create_sql)
    existing_columns = _fetch_existing_columns(conn, table_name)

    for column_name, column_definition in required_columns:
        if column_name not in existing_columns:
            conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
            )


def run_integrity_check(conn: sqlite3.Connection) -> None:
    """Validate DB integrity and raise if a problem is reported."""

    result = conn.execute("PRAGMA integrity_check").fetchone()
    status = result[0] if result else None
    if status != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {status}")


def init_db(
    preferred_path: str | os.PathLike[str] | None = None,
) -> tuple[sqlite3.Connection, Path]:
    """Initialize SQLite DB with path resolution, integrity check and migrations."""

    db_path = resolve_writable_db_path(preferred_path)
    conn = sqlite3.connect(db_path)

    try:
        conn.execute("PRAGMA foreign_keys = ON")
        run_integrity_check(conn)

        ensure_table_schema(
            conn,
            "players",
            PLAYERS_BASE_SQL,
            [
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("user_id", "TEXT NOT NULL UNIQUE"),
                ("display_name", "TEXT"),
                ("created_at_utc", "TEXT NOT NULL"),
            ],
        )

        ensure_table_schema(
            conn,
            "annals",
            ANNALS_BASE_SQL,
            [
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("event_type", "TEXT NOT NULL"),
                ("payload_json", "TEXT"),
                ("timestamp_utc", "TEXT NOT NULL"),
            ],
        )

        conn.execute(FAILURE_LOGS_SQL)
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise

    return conn, db_path

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .config import settings

DEFAULT_DB_PATH = settings.db_path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    partner_id TEXT NOT NULL DEFAULT 'demo-enterprise-partner',
    client_name TEXT NOT NULL,
    site_id TEXT NOT NULL,
    province TEXT NOT NULL,
    scada_status TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    initial_eta_hours REAL NOT NULL,
    current_eta_hours REAL NOT NULL,
    severity TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    hold_until TEXT NOT NULL,
    restored_at TEXT,
    restored_by TEXT,
    dispatch_decision TEXT NOT NULL,
    timeout_applied INTEGER NOT NULL DEFAULT 0,
    last_signal_at TEXT,
    source_event_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    severity TEXT NOT NULL,
    predicted_eta_hours REAL NOT NULL,
    extracted_keywords_json TEXT NOT NULL,
    observed_at TEXT,
    source_signal_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(incident_id) REFERENCES incidents(id)
);

CREATE TABLE IF NOT EXISTS incident_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    previous_eta_hours REAL,
    new_eta_hours REAL,
    reason_code TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    confidence_band TEXT NOT NULL,
    feature_snapshot_json TEXT NOT NULL,
    observed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(incident_id) REFERENCES incidents(id)
);

"""


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | Path | None = None) -> None:
    conn = get_connection(db_path)
    try:
        with conn:
            conn.executescript(SCHEMA_SQL)
            _ensure_column(conn, "incidents", "partner_id", "TEXT NOT NULL DEFAULT 'demo-enterprise-partner'")
            _ensure_column(conn, "incidents", "source_event_id", "TEXT")
            _ensure_column(conn, "signals", "observed_at", "TEXT")
            _ensure_column(conn, "signals", "source_signal_id", "TEXT")
            conn.execute("DROP INDEX IF EXISTS idx_incidents_source_event_id")
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_incidents_partner_source_event_id
                ON incidents(partner_id, source_event_id)
                WHERE source_event_id IS NOT NULL
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_source_signal_id
                ON signals(source_signal_id)
                WHERE source_signal_id IS NOT NULL
                """
            )
            conn.commit()
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def fetch_one(conn: sqlite3.Connection, sql: str, params: Iterable | None = None):
    cur = conn.execute(sql, tuple(params or ()))
    return cur.fetchone()


def fetch_all(conn: sqlite3.Connection, sql: str, params: Iterable | None = None):
    cur = conn.execute(sql, tuple(params or ()))
    return cur.fetchall()

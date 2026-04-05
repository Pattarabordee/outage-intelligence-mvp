from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Iterable

DEFAULT_DB_PATH = Path(tempfile.gettempdir()) / "outage_intelligence_demo.db"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
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
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def fetch_one(conn: sqlite3.Connection, sql: str, params: Iterable | None = None):
    cur = conn.execute(sql, tuple(params or ()))
    return cur.fetchone()


def fetch_all(conn: sqlite3.Connection, sql: str, params: Iterable | None = None):
    cur = conn.execute(sql, tuple(params or ()))
    return cur.fetchall()

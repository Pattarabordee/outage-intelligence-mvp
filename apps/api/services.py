from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .database import fetch_all, fetch_one, get_connection, init_db
from .rules import TIMEOUT_MINUTES, TIMEOUT_WORST_CASE_HOURS, evaluate_text_signal, initial_eta_from_scada, recommendation_from_eta


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def dtstr(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def row_to_incident(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "client_name": row["client_name"],
        "site_id": row["site_id"],
        "province": row["province"],
        "scada_status": row["scada_status"],
        "status": row["status"],
        "created_at": parse_dt(row["created_at"]),
        "updated_at": parse_dt(row["updated_at"]),
        "initial_eta_hours": row["initial_eta_hours"],
        "current_eta_hours": row["current_eta_hours"],
        "severity": row["severity"],
        "reason_code": row["reason_code"],
        "hold_until": parse_dt(row["hold_until"]),
        "restored_at": parse_dt(row["restored_at"]),
        "restored_by": row["restored_by"],
        "dispatch_decision": row["dispatch_decision"],
        "timeout_applied": bool(row["timeout_applied"]),
        "last_signal_at": parse_dt(row["last_signal_at"]),
        "metadata": json.loads(row["metadata_json"] or "{}"),
    }


def row_to_signal(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "incident_id": row["incident_id"],
        "channel": row["channel"],
        "raw_text": row["raw_text"],
        "normalized_text": row["normalized_text"],
        "severity": row["severity"],
        "predicted_eta_hours": row["predicted_eta_hours"],
        "extracted_keywords": json.loads(row["extracted_keywords_json"] or "[]"),
        "created_at": parse_dt(row["created_at"]),
    }


class IncidentService:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path
        init_db(self.db_path)

    def _conn(self):
        return get_connection(self.db_path)

    def create_incident(self, client_name: str, site_id: str, province: str, scada_status: str) -> dict:
        now = utcnow()
        eta = initial_eta_from_scada(scada_status)
        incident_id = f"INC-{uuid.uuid4().hex[:10].upper()}"
        hold_until = now + timedelta(hours=eta)
        recommendation = recommendation_from_eta(eta)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO incidents (
                    id, client_name, site_id, province, scada_status, status, created_at,
                    updated_at, initial_eta_hours, current_eta_hours, severity, reason_code,
                    hold_until, restored_at, restored_by, dispatch_decision, timeout_applied,
                    last_signal_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    client_name,
                    site_id,
                    province,
                    scada_status,
                    "HOLD_SENT",
                    dtstr(now),
                    dtstr(now),
                    eta,
                    eta,
                    "baseline",
                    "SCADA_INITIAL_ASSESSMENT",
                    dtstr(hold_until),
                    None,
                    None,
                    recommendation,
                    0,
                    None,
                    json.dumps({"timeout_minutes": TIMEOUT_MINUTES}),
                ),
            )
            conn.commit()
        return self.get_incident(incident_id)

    def get_incident(self, incident_id: str) -> dict:
        with self._conn() as conn:
            row = fetch_one(conn, "SELECT * FROM incidents WHERE id = ?", (incident_id,))
            if not row:
                raise KeyError(f"Incident not found: {incident_id}")
            return row_to_incident(row)

    def list_incidents(self) -> list[dict]:
        with self._conn() as conn:
            rows = fetch_all(conn, "SELECT * FROM incidents ORDER BY created_at DESC")
            return [row_to_incident(r) for r in rows]

    def list_signals(self, incident_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = fetch_all(conn, "SELECT * FROM signals WHERE incident_id = ? ORDER BY created_at ASC", (incident_id,))
            return [row_to_signal(r) for r in rows]

    def add_field_signal(self, incident_id: str, channel: str, raw_text: str) -> tuple[dict, dict]:
        incident = self.get_incident(incident_id)
        rule = evaluate_text_signal(raw_text)
        now = utcnow()
        new_eta = rule.predicted_eta_hours
        if rule.severity == "resolved":
            return self.restore_incident(incident_id, restored_by="DISPATCHER"), {
                "id": -1,
                "incident_id": incident_id,
                "channel": channel,
                "raw_text": raw_text,
                "normalized_text": rule.normalized_text,
                "severity": rule.severity,
                "predicted_eta_hours": new_eta,
                "extracted_keywords": rule.extracted_keywords,
                "created_at": now,
            }

        hold_until = now + timedelta(hours=new_eta)
        recommendation = recommendation_from_eta(new_eta)
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO signals (
                    incident_id, channel, raw_text, normalized_text, severity,
                    predicted_eta_hours, extracted_keywords_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    channel,
                    raw_text,
                    rule.normalized_text,
                    rule.severity,
                    new_eta,
                    json.dumps(rule.extracted_keywords),
                    dtstr(now),
                ),
            )
            conn.execute(
                """
                UPDATE incidents
                SET status = ?, updated_at = ?, current_eta_hours = ?, severity = ?,
                    reason_code = ?, hold_until = ?, dispatch_decision = ?, last_signal_at = ?
                WHERE id = ?
                """,
                (
                    "ETA_REVISED",
                    dtstr(now),
                    new_eta,
                    rule.severity,
                    rule.reason_code,
                    dtstr(hold_until),
                    recommendation,
                    dtstr(now),
                    incident_id,
                ),
            )
            conn.commit()
            signal_id = cur.lastrowid
        return self.get_incident(incident_id), {
            "id": signal_id,
            "incident_id": incident_id,
            "channel": channel,
            "raw_text": raw_text,
            "normalized_text": rule.normalized_text,
            "severity": rule.severity,
            "predicted_eta_hours": new_eta,
            "extracted_keywords": rule.extracted_keywords,
            "created_at": now,
        }

    def apply_timeout_if_needed(self, incident_id: str) -> dict:
        incident = self.get_incident(incident_id)
        if incident["restored_at"] is not None or incident["status"] == "CLOSED":
            return incident

        last_reference = incident["last_signal_at"] or incident["created_at"]
        minutes_elapsed = (utcnow() - last_reference).total_seconds() / 60.0
        if minutes_elapsed < TIMEOUT_MINUTES:
            return incident

        now = utcnow()
        new_eta = TIMEOUT_WORST_CASE_HOURS
        recommendation = recommendation_from_eta(new_eta)
        hold_until = now + timedelta(hours=new_eta)
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE incidents
                SET status = ?, updated_at = ?, current_eta_hours = ?, severity = ?, reason_code = ?,
                    hold_until = ?, dispatch_decision = ?, timeout_applied = 1
                WHERE id = ?
                """,
                (
                    "ETA_REVISED",
                    dtstr(now),
                    new_eta,
                    "timeout_worst_case",
                    "TIMEOUT_FAILSAFE",
                    dtstr(hold_until),
                    recommendation,
                    incident_id,
                ),
            )
            conn.commit()
        return self.get_incident(incident_id)

    def force_backdate_incident(self, incident_id: str, minutes_ago: int) -> dict:
        reference = utcnow() - timedelta(minutes=minutes_ago)
        with self._conn() as conn:
            conn.execute(
                "UPDATE incidents SET created_at = ?, updated_at = ? WHERE id = ?",
                (dtstr(reference), dtstr(reference), incident_id),
            )
            conn.commit()
        return self.get_incident(incident_id)

    def restore_incident(self, incident_id: str, restored_by: str) -> dict:
        now = utcnow()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE incidents
                SET status = ?, updated_at = ?, current_eta_hours = ?, severity = ?, reason_code = ?,
                    hold_until = ?, restored_at = ?, restored_by = ?, dispatch_decision = ?
                WHERE id = ?
                """,
                (
                    "CLOSED",
                    dtstr(now),
                    0.0,
                    "resolved",
                    "RESTORED",
                    dtstr(now),
                    dtstr(now),
                    restored_by,
                    "CLOSE_TICKET_AND_LOG_GROUND_TRUTH",
                    incident_id,
                ),
            )
            conn.commit()
        return self.get_incident(incident_id)

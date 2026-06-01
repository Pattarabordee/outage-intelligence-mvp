from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .database import fetch_all, fetch_one, get_connection, init_db
from .exceptions import StateConflictError
from .observability import log_event
from .rules import (
    POLICY_VERSION,
    TIMEOUT_MINUTES,
    TIMEOUT_WORST_CASE_HOURS,
    confidence_band,
    evaluate_text_signal,
    initial_eta_from_scada,
    partner_action_from_recommendation,
    policy_explanation,
    recommendation_from_eta,
)
from .types import JSONDict


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def dtstr(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _loads_json(value: str | None, fallback):
    return json.loads(value) if value else fallback


def row_to_incident(row: sqlite3.Row) -> JSONDict:
    return {
        "id": row["id"],
        "partner_id": row["partner_id"],
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
        "source_event_id": row["source_event_id"],
        "metadata": _loads_json(row["metadata_json"], {}),
    }


def row_to_signal(row: sqlite3.Row) -> JSONDict:
    return {
        "id": row["id"],
        "incident_id": row["incident_id"],
        "channel": row["channel"],
        "raw_text": row["raw_text"],
        "normalized_text": row["normalized_text"],
        "severity": row["severity"],
        "predicted_eta_hours": row["predicted_eta_hours"],
        "extracted_keywords": _loads_json(row["extracted_keywords_json"], []),
        "observed_at": parse_dt(row["observed_at"]),
        "source_signal_id": row["source_signal_id"],
        "created_at": parse_dt(row["created_at"]),
    }


def row_to_event(row: sqlite3.Row) -> JSONDict:
    return {
        "id": row["id"],
        "incident_id": row["incident_id"],
        "event_type": row["event_type"],
        "source": row["source"],
        "previous_eta_hours": row["previous_eta_hours"],
        "new_eta_hours": row["new_eta_hours"],
        "reason_code": row["reason_code"],
        "policy_version": row["policy_version"],
        "confidence_band": row["confidence_band"],
        "feature_snapshot": _loads_json(row["feature_snapshot_json"], {}),
        "observed_at": parse_dt(row["observed_at"]),
        "created_at": parse_dt(row["created_at"]),
    }


class IncidentService:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path
        init_db(self.db_path)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = get_connection(self.db_path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def create_incident(
        self,
        partner_id: str,
        client_name: str,
        site_id: str,
        province: str,
        scada_status: str,
        source_event_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[JSONDict, bool]:
        idempotency_value = source_event_id or idempotency_key
        if idempotency_value:
            existing = self.get_incident_by_source_event_id(partner_id, idempotency_value)
            if existing:
                log_event("duplicate_incident_ignored", partner_id=partner_id, source_event_id=idempotency_value)
                return existing, False

        now = utcnow()
        eta = initial_eta_from_scada(scada_status)
        incident_id = f"INC-{uuid.uuid4().hex[:10].upper()}"
        hold_until = now + timedelta(hours=eta)
        recommendation = recommendation_from_eta(eta)
        metadata = {
            "timeout_minutes": TIMEOUT_MINUTES,
            "policy_version": POLICY_VERSION,
        }
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO incidents (
                    id, partner_id, client_name, site_id, province, scada_status, status, created_at,
                    updated_at, initial_eta_hours, current_eta_hours, severity, reason_code,
                    hold_until, restored_at, restored_by, dispatch_decision, timeout_applied,
                    last_signal_at, source_event_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    partner_id,
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
                    idempotency_value,
                    json.dumps(metadata),
                ),
            )
            self._insert_event(
                conn,
                incident_id=incident_id,
                event_type="INCIDENT_CREATED",
                source="API",
                previous_eta_hours=None,
                new_eta_hours=eta,
                reason_code="SCADA_INITIAL_ASSESSMENT",
                severity="baseline",
                feature_snapshot={
                    "partner_id": partner_id,
                    "scada_status": scada_status,
                    "site_id": site_id,
                    "province": province,
                },
                observed_at=now,
                created_at=now,
            )
            conn.commit()
        log_event("incident_created", incident_id=incident_id, partner_id=partner_id, reason_code="SCADA_INITIAL_ASSESSMENT")
        return self.get_incident(incident_id), True

    def get_incident_by_source_event_id(self, partner_id: str, source_event_id: str) -> JSONDict | None:
        with self._conn() as conn:
            row = fetch_one(
                conn,
                "SELECT * FROM incidents WHERE partner_id = ? AND source_event_id = ?",
                (partner_id, source_event_id),
            )
            return row_to_incident(row) if row else None

    def get_incident(self, incident_id: str) -> JSONDict:
        with self._conn() as conn:
            row = fetch_one(conn, "SELECT * FROM incidents WHERE id = ?", (incident_id,))
            if not row:
                raise KeyError(f"Incident not found: {incident_id}")
            return row_to_incident(row)

    def list_incidents(self, partner_id: str | None = None) -> list[JSONDict]:
        with self._conn() as conn:
            if partner_id:
                rows = fetch_all(conn, "SELECT * FROM incidents WHERE partner_id = ? ORDER BY created_at DESC", (partner_id,))
            else:
                rows = fetch_all(conn, "SELECT * FROM incidents ORDER BY created_at DESC")
            return [row_to_incident(r) for r in rows]

    def list_signals(self, incident_id: str) -> list[JSONDict]:
        with self._conn() as conn:
            rows = fetch_all(conn, "SELECT * FROM signals WHERE incident_id = ? ORDER BY created_at ASC", (incident_id,))
            return [row_to_signal(r) for r in rows]

    def list_events(self, incident_id: str) -> list[JSONDict]:
        with self._conn() as conn:
            rows = fetch_all(conn, "SELECT * FROM incident_events WHERE incident_id = ? ORDER BY created_at ASC", (incident_id,))
            return [row_to_event(r) for r in rows]

    def add_field_signal(
        self,
        incident_id: str,
        channel: str,
        raw_text: str,
        observed_at: datetime | None = None,
        source_signal_id: str | None = None,
    ) -> tuple[JSONDict, JSONDict]:
        incident = self.get_incident(incident_id)
        if incident["status"] == "CLOSED":
            raise StateConflictError(f"Incident is already closed: {incident_id}")

        if source_signal_id:
            existing = self.get_signal_by_source_signal_id(source_signal_id)
            if existing:
                if existing["incident_id"] != incident_id:
                    raise StateConflictError("source_signal_id already belongs to another incident")
                log_event("duplicate_signal_ignored", incident_id=existing["incident_id"], source_signal_id=source_signal_id)
                return self.get_incident(existing["incident_id"]), existing

        rule = evaluate_text_signal(raw_text)
        now = utcnow()
        observed = observed_at or now
        new_eta = rule.predicted_eta_hours
        with self._conn() as conn:
            signal = self._insert_signal(
                conn,
                incident_id=incident_id,
                channel=channel,
                raw_text=raw_text,
                rule=rule,
                observed_at=observed,
                source_signal_id=source_signal_id,
                created_at=now,
            )
            if rule.severity == "resolved":
                self._close_incident(
                    conn,
                    incident_id=incident_id,
                    restored_by="DISPATCHER",
                    now=now,
                    previous_eta_hours=incident["current_eta_hours"],
                    source="FIELD_SIGNAL",
                    observed_at=observed,
                )
                log_event("incident_closed", incident_id=incident_id, partner_id=incident["partner_id"], source="FIELD_SIGNAL")
            else:
                hold_until = now + timedelta(hours=new_eta)
                recommendation = recommendation_from_eta(new_eta)
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
                self._insert_event(
                    conn,
                    incident_id=incident_id,
                    event_type="ETA_REVISED",
                    source=channel,
                    previous_eta_hours=incident["current_eta_hours"],
                    new_eta_hours=new_eta,
                    reason_code=rule.reason_code,
                    severity=rule.severity,
                    feature_snapshot={
                        "channel": channel,
                        "keywords": rule.extracted_keywords,
                        "normalized_text": rule.normalized_text,
                    },
                    observed_at=observed,
                    created_at=now,
                )
                log_event(
                    "eta_revised",
                    incident_id=incident_id,
                    partner_id=incident["partner_id"],
                    reason_code=rule.reason_code,
                    eta_hours=new_eta,
                )
            conn.commit()
        return self.get_incident(incident_id), signal

    def get_signal_by_source_signal_id(self, source_signal_id: str) -> JSONDict | None:
        with self._conn() as conn:
            row = fetch_one(conn, "SELECT * FROM signals WHERE source_signal_id = ?", (source_signal_id,))
            return row_to_signal(row) if row else None

    def apply_timeout_if_needed(self, incident_id: str) -> JSONDict:
        incident = self.get_incident(incident_id)
        if incident["restored_at"] is not None or incident["status"] == "CLOSED" or incident["timeout_applied"]:
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
            self._insert_event(
                conn,
                incident_id=incident_id,
                event_type="TIMEOUT_APPLIED",
                source="TIMEOUT_CHECK",
                previous_eta_hours=incident["current_eta_hours"],
                new_eta_hours=new_eta,
                reason_code="TIMEOUT_FAILSAFE",
                severity="timeout_worst_case",
                feature_snapshot={
                    "minutes_elapsed": minutes_elapsed,
                    "timeout_minutes": TIMEOUT_MINUTES,
                },
                observed_at=now,
                created_at=now,
            )
            conn.commit()
        log_event("timeout_applied", incident_id=incident_id, partner_id=incident["partner_id"], eta_hours=new_eta)
        return self.get_incident(incident_id)

    def force_backdate_incident(self, incident_id: str, minutes_ago: int) -> JSONDict:
        reference = utcnow() - timedelta(minutes=minutes_ago)
        with self._conn() as conn:
            conn.execute(
                "UPDATE incidents SET created_at = ?, updated_at = ? WHERE id = ?",
                (dtstr(reference), dtstr(reference), incident_id),
            )
            conn.commit()
        return self.get_incident(incident_id)

    def restore_incident(self, incident_id: str, restored_by: str) -> JSONDict:
        incident = self.get_incident(incident_id)
        if incident["status"] == "CLOSED":
            return incident

        now = utcnow()
        with self._conn() as conn:
            self._close_incident(
                conn,
                incident_id=incident_id,
                restored_by=restored_by,
                now=now,
                previous_eta_hours=incident["current_eta_hours"],
                source=restored_by,
                observed_at=now,
            )
            conn.commit()
        log_event("incident_closed", incident_id=incident_id, partner_id=incident["partner_id"], source=restored_by)
        return self.get_incident(incident_id)

    def decision_for_incident(self, incident: JSONDict) -> JSONDict:
        recommendation = incident["dispatch_decision"]
        return {
            "eta_hours": incident["current_eta_hours"],
            "recommendation": recommendation,
            "partner_action": partner_action_from_recommendation(recommendation),
            "confidence_band": confidence_band(incident["severity"]),
            "reason_code": incident["reason_code"],
            "policy_version": incident["metadata"].get("policy_version", POLICY_VERSION),
            "prediction_time": incident["updated_at"],
            "policy_explanation": policy_explanation(incident["reason_code"], incident["current_eta_hours"]),
            "sla_behavior": {
                "timeout_minutes": incident["metadata"].get("timeout_minutes", TIMEOUT_MINUTES),
                "timeout_fallback_eta_hours": TIMEOUT_WORST_CASE_HOURS,
                "idempotency_fields": ["source_event_id", "idempotency_key", "source_signal_id"],
            },
        }

    def export_closed_incidents_dataset(self) -> list[JSONDict]:
        with self._conn() as conn:
            rows = fetch_all(conn, "SELECT * FROM incidents WHERE status = 'CLOSED' ORDER BY restored_at ASC")
        dataset = []
        for row in rows:
            incident = row_to_incident(row)
            duration = (incident["restored_at"] - incident["created_at"]).total_seconds() / 3600.0
            eta_error = incident["initial_eta_hours"] - duration
            dataset.append(
                {
                    "incident_id": incident["id"],
                    "prediction_time": dtstr(incident["created_at"]),
                    "actual_restoration_duration_hours": round(duration, 3),
                    "initial_eta_hours": incident["initial_eta_hours"],
                    "eta_error_hours": round(eta_error, 3),
                    "rule_version": incident["metadata"].get("policy_version", POLICY_VERSION),
                    "feature_snapshot": {
                        "partner_id": incident["partner_id"],
                        "scada_status": incident["scada_status"],
                        "province": incident["province"],
                        "source_event_id_present": bool(incident["source_event_id"]),
                        "timeout_applied": incident["timeout_applied"],
                    },
                }
            )
        return dataset

    def _insert_signal(
        self,
        conn: sqlite3.Connection,
        incident_id: str,
        channel: str,
        raw_text: str,
        rule,
        observed_at: datetime,
        source_signal_id: str | None,
        created_at: datetime,
    ) -> JSONDict:
        cur = conn.execute(
            """
            INSERT INTO signals (
                incident_id, channel, raw_text, normalized_text, severity,
                predicted_eta_hours, extracted_keywords_json, observed_at, source_signal_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident_id,
                channel,
                raw_text,
                rule.normalized_text,
                rule.severity,
                rule.predicted_eta_hours,
                json.dumps(rule.extracted_keywords),
                dtstr(observed_at),
                source_signal_id,
                dtstr(created_at),
            ),
        )
        return {
            "id": cur.lastrowid,
            "incident_id": incident_id,
            "channel": channel,
            "raw_text": raw_text,
            "normalized_text": rule.normalized_text,
            "severity": rule.severity,
            "predicted_eta_hours": rule.predicted_eta_hours,
            "extracted_keywords": rule.extracted_keywords,
            "observed_at": observed_at,
            "source_signal_id": source_signal_id,
            "created_at": created_at,
        }

    def _close_incident(
        self,
        conn: sqlite3.Connection,
        incident_id: str,
        restored_by: str,
        now: datetime,
        previous_eta_hours: float,
        source: str,
        observed_at: datetime,
    ) -> None:
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
        self._insert_event(
            conn,
            incident_id=incident_id,
            event_type="INCIDENT_CLOSED",
            source=source,
            previous_eta_hours=previous_eta_hours,
            new_eta_hours=0.0,
            reason_code="RESTORED",
            severity="resolved",
            feature_snapshot={"restored_by": restored_by},
            observed_at=observed_at,
            created_at=now,
        )

    def _insert_event(
        self,
        conn: sqlite3.Connection,
        incident_id: str,
        event_type: str,
        source: str,
        previous_eta_hours: float | None,
        new_eta_hours: float | None,
        reason_code: str,
        severity: str,
        feature_snapshot: JSONDict,
        observed_at: datetime | None,
        created_at: datetime,
    ) -> None:
        conn.execute(
            """
            INSERT INTO incident_events (
                incident_id, event_type, source, previous_eta_hours, new_eta_hours,
                reason_code, policy_version, confidence_band, feature_snapshot_json,
                observed_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident_id,
                event_type,
                source,
                previous_eta_hours,
                new_eta_hours,
                reason_code,
                POLICY_VERSION,
                confidence_band(severity),
                json.dumps(feature_snapshot),
                dtstr(observed_at),
                dtstr(created_at),
            ),
        )

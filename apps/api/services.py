from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import settings
from .database import fetch_all, fetch_one, get_connection, init_db
from .exceptions import AccessDeniedError, StateConflictError
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
from .webhooks import build_webhook_headers, canonical_json


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


def row_to_partner_profile(row: sqlite3.Row) -> JSONDict:
    return {
        "partner_id": row["partner_id"],
        "display_name": row["display_name"],
        "partner_class": row["partner_class"],
        "allowed_site_prefixes": _loads_json(row["allowed_site_prefixes_json"], []),
        "webhook_mode": row["webhook_mode"],
        "notification_contact_label": row["notification_contact_label"],
        "created_at": parse_dt(row["created_at"]),
        "updated_at": parse_dt(row["updated_at"]),
    }


def row_to_webhook_delivery(row: sqlite3.Row) -> JSONDict:
    return {
        "event_id": row["event_id"],
        "partner_id": row["partner_id"],
        "incident_id": row["incident_id"],
        "event_type": row["event_type"],
        "payload": _loads_json(row["payload_json"], {}),
        "headers": _loads_json(row["headers_json"], {}),
        "status": row["status"],
        "attempt_count": row["attempt_count"],
        "max_attempts": row["max_attempts"],
        "next_attempt_at": parse_dt(row["next_attempt_at"]),
        "last_error": row["last_error"],
        "created_at": parse_dt(row["created_at"]),
        "updated_at": parse_dt(row["updated_at"]),
    }


def row_to_webhook_attempt(row: sqlite3.Row) -> JSONDict:
    return {
        "id": row["id"],
        "event_id": row["event_id"],
        "attempt_number": row["attempt_number"],
        "outcome": row["outcome"],
        "response_status": row["response_status"],
        "error_message": row["error_message"],
        "created_at": parse_dt(row["created_at"]),
    }


class IncidentService:
    def __init__(
        self,
        db_path: str | Path | None = None,
        webhook_secret: str | None = None,
        webhook_max_attempts: int | None = None,
    ):
        self.db_path = db_path
        self.webhook_secret = webhook_secret if webhook_secret is not None else settings.webhook_secret
        self.webhook_max_attempts = webhook_max_attempts or settings.webhook_max_attempts
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
        self.ensure_partner_profile(partner_id, display_name=client_name)
        self.validate_partner_site_scope(partner_id, site_id)
        idempotency_value = source_event_id or idempotency_key
        if idempotency_value:
            existing = self.get_incident_by_source_event_id(partner_id, idempotency_value)
            if existing:
                log_event("duplicate_incident_ignored", partner_id=partner_id, source_event_id=idempotency_value)
                self.enqueue_webhook_delivery(existing, "duplicate.ignored")
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
        incident = self.get_incident(incident_id)
        self.enqueue_webhook_delivery(incident, "incident.created")
        return incident, True

    def ensure_partner_profile(self, partner_id: str, display_name: str | None = None) -> JSONDict:
        existing = self.get_partner_profile(partner_id)
        if existing:
            return existing

        now = utcnow()
        profile = {
            "partner_id": partner_id,
            "display_name": display_name or "Demo Enterprise Partner",
            "partner_class": "enterprise_sandbox",
            "allowed_site_prefixes": ["SITE-"],
            "webhook_mode": "outbox_only",
            "notification_contact_label": "Sandbox operations queue",
            "created_at": now,
            "updated_at": now,
        }
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO partner_profiles (
                    partner_id, display_name, partner_class, allowed_site_prefixes_json,
                    webhook_mode, notification_contact_label, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile["partner_id"],
                    profile["display_name"],
                    profile["partner_class"],
                    json.dumps(profile["allowed_site_prefixes"]),
                    profile["webhook_mode"],
                    profile["notification_contact_label"],
                    dtstr(now),
                    dtstr(now),
                ),
            )
            conn.commit()
        log_event("partner_profile_created", partner_id=partner_id, partner_class=profile["partner_class"])
        return profile

    def upsert_partner_profile(
        self,
        partner_id: str,
        display_name: str,
        partner_class: str,
        allowed_site_prefixes: list[str],
        webhook_mode: str,
        notification_contact_label: str | None,
    ) -> JSONDict:
        now = utcnow()
        existing = self.get_partner_profile(partner_id)
        created_at = existing["created_at"] if existing else now
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO partner_profiles (
                    partner_id, display_name, partner_class, allowed_site_prefixes_json,
                    webhook_mode, notification_contact_label, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(partner_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    partner_class = excluded.partner_class,
                    allowed_site_prefixes_json = excluded.allowed_site_prefixes_json,
                    webhook_mode = excluded.webhook_mode,
                    notification_contact_label = excluded.notification_contact_label,
                    updated_at = excluded.updated_at
                """,
                (
                    partner_id,
                    display_name,
                    partner_class,
                    json.dumps(allowed_site_prefixes),
                    webhook_mode,
                    notification_contact_label,
                    dtstr(created_at),
                    dtstr(now),
                ),
            )
            conn.commit()
        log_event("partner_profile_upserted", partner_id=partner_id, partner_class=partner_class)
        return self.get_partner_profile(partner_id) or self.ensure_partner_profile(partner_id, display_name)

    def get_partner_profile(self, partner_id: str) -> JSONDict | None:
        with self._conn() as conn:
            row = fetch_one(conn, "SELECT * FROM partner_profiles WHERE partner_id = ?", (partner_id,))
            return row_to_partner_profile(row) if row else None

    def list_partner_profiles(self) -> list[JSONDict]:
        with self._conn() as conn:
            rows = fetch_all(conn, "SELECT * FROM partner_profiles ORDER BY partner_id ASC")
            return [row_to_partner_profile(row) for row in rows]

    def validate_partner_site_scope(self, partner_id: str, site_id: str) -> None:
        profile = self.get_partner_profile(partner_id)
        prefixes = profile["allowed_site_prefixes"] if profile else []
        if prefixes and not any(site_id.startswith(prefix) for prefix in prefixes):
            raise AccessDeniedError(f"site_id is outside the partner sandbox scope: {site_id}")

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

    def list_all_events(self) -> list[JSONDict]:
        with self._conn() as conn:
            rows = fetch_all(conn, "SELECT * FROM incident_events ORDER BY created_at ASC")
            return [row_to_event(row) for row in rows]

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
        updated_incident = self.get_incident(incident_id)
        webhook_event_type = "incident.restored" if updated_incident["status"] == "CLOSED" else "eta.revised"
        self.enqueue_webhook_delivery(updated_incident, webhook_event_type)
        return updated_incident, signal

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
        updated_incident = self.get_incident(incident_id)
        self.enqueue_webhook_delivery(updated_incident, "timeout.applied")
        return updated_incident

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
        updated_incident = self.get_incident(incident_id)
        self.enqueue_webhook_delivery(updated_incident, "incident.restored")
        return updated_incident

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

    def enqueue_webhook_delivery(self, incident: JSONDict, event_type: str) -> JSONDict:
        now = utcnow()
        event_id = f"evt-{uuid.uuid4().hex[:12]}"
        payload = {
            "event_id": event_id,
            "event_type": event_type,
            "partner_id": incident["partner_id"],
            "incident_id": incident["id"],
            "occurred_at": dtstr(now),
            "decision": self.decision_for_incident(incident),
        }
        payload_json = canonical_json(payload)
        headers = build_webhook_headers(
            payload_json=payload_json,
            partner_id=incident["partner_id"],
            event_id=event_id,
            occurred_at=dtstr(now) or "",
            secret=self.webhook_secret,
        )
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO webhook_deliveries (
                    event_id, partner_id, incident_id, event_type, payload_json,
                    headers_json, status, attempt_count, max_attempts,
                    next_attempt_at, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    incident["partner_id"],
                    incident["id"],
                    event_type,
                    payload_json,
                    json.dumps(headers, sort_keys=True),
                    "queued",
                    0,
                    self.webhook_max_attempts,
                    None,
                    None,
                    dtstr(now),
                    dtstr(now),
                ),
            )
            conn.commit()
        log_event(
            "webhook_queued",
            event_id=event_id,
            partner_id=incident["partner_id"],
            webhook_event_type=event_type,
        )
        return self.get_webhook_delivery(event_id)

    def list_webhook_deliveries(self, partner_id: str | None = None) -> list[JSONDict]:
        with self._conn() as conn:
            if partner_id:
                rows = fetch_all(
                    conn,
                    "SELECT * FROM webhook_deliveries WHERE partner_id = ? ORDER BY created_at ASC",
                    (partner_id,),
                )
            else:
                rows = fetch_all(conn, "SELECT * FROM webhook_deliveries ORDER BY created_at ASC")
            return [row_to_webhook_delivery(row) for row in rows]

    def get_webhook_delivery(self, event_id: str) -> JSONDict:
        with self._conn() as conn:
            row = fetch_one(conn, "SELECT * FROM webhook_deliveries WHERE event_id = ?", (event_id,))
            if not row:
                raise KeyError(f"Webhook delivery not found: {event_id}")
            return row_to_webhook_delivery(row)

    def retry_webhook_delivery(self, event_id: str) -> JSONDict:
        delivery = self.get_webhook_delivery(event_id)
        if delivery["status"] == "delivered":
            raise StateConflictError(f"Webhook delivery is already delivered: {event_id}")
        now = utcnow()
        next_attempt_count = delivery["attempt_count"] + 1
        if delivery["attempt_count"] >= delivery["max_attempts"]:
            status = "exhausted"
            next_attempt_at = None
            last_error = "Maximum retry attempts reached"
        else:
            status = "retry_scheduled"
            next_attempt_at = now + timedelta(minutes=2 ** max(delivery["attempt_count"], 0))
            last_error = "Local sandbox retry scheduled; no outbound HTTP was sent."

        with self._conn() as conn:
            conn.execute(
                """
                UPDATE webhook_deliveries
                SET status = ?, attempt_count = ?, next_attempt_at = ?, last_error = ?, updated_at = ?
                WHERE event_id = ?
                """,
                (
                    status,
                    min(next_attempt_count, delivery["max_attempts"]),
                    dtstr(next_attempt_at),
                    last_error,
                    dtstr(now),
                    event_id,
                ),
            )
            conn.commit()
        log_event("webhook_retry_requested", event_id=event_id, partner_id=delivery["partner_id"], status=status)
        return self.get_webhook_delivery(event_id)

    def record_webhook_attempt(
        self,
        event_id: str,
        outcome: str,
        response_status: int | None = None,
        error_message: str | None = None,
    ) -> JSONDict:
        delivery = self.get_webhook_delivery(event_id)
        if delivery["status"] == "delivered":
            raise StateConflictError(f"Webhook delivery is already delivered: {event_id}")

        now = utcnow()
        attempt_number = delivery["attempt_count"] + 1
        if outcome == "delivered":
            delivery_status = "delivered"
            next_attempt_at = None
            last_error = None
        else:
            if attempt_number >= delivery["max_attempts"]:
                delivery_status = "exhausted"
                next_attempt_at = None
            else:
                delivery_status = "retry_scheduled"
                next_attempt_at = now + timedelta(minutes=2 ** max(attempt_number - 1, 0))
            last_error = error_message or "Sandbox delivery attempt failed."

        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO webhook_delivery_attempts (
                    event_id, attempt_number, outcome, response_status, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, attempt_number, outcome, response_status, error_message, dtstr(now)),
            )
            conn.execute(
                """
                UPDATE webhook_deliveries
                SET status = ?, attempt_count = ?, next_attempt_at = ?, last_error = ?, updated_at = ?
                WHERE event_id = ?
                """,
                (
                    delivery_status,
                    attempt_number,
                    dtstr(next_attempt_at),
                    last_error,
                    dtstr(now),
                    event_id,
                ),
            )
            conn.commit()
            attempt_id = cur.lastrowid
        log_event(
            "webhook_attempt_recorded",
            event_id=event_id,
            partner_id=delivery["partner_id"],
            outcome=outcome,
            delivery_status=delivery_status,
        )
        return {
            "delivery": self.get_webhook_delivery(event_id),
            "attempt": self.get_webhook_attempt(attempt_id),
        }

    def get_webhook_attempt(self, attempt_id: int) -> JSONDict:
        with self._conn() as conn:
            row = fetch_one(conn, "SELECT * FROM webhook_delivery_attempts WHERE id = ?", (attempt_id,))
            if not row:
                raise KeyError(f"Webhook delivery attempt not found: {attempt_id}")
            return row_to_webhook_attempt(row)

    def list_webhook_attempts(self, event_id: str) -> list[JSONDict]:
        with self._conn() as conn:
            rows = fetch_all(
                conn,
                "SELECT * FROM webhook_delivery_attempts WHERE event_id = ? ORDER BY attempt_number ASC",
                (event_id,),
            )
            return [row_to_webhook_attempt(row) for row in rows]

    def executive_summary(self) -> JSONDict:
        incidents = self.list_incidents()
        events = self.list_all_events()
        deliveries = self.list_webhook_deliveries()
        profiles = self.list_partner_profiles()
        closed_dataset = self.export_closed_incidents_dataset()

        incidents_by_id = {incident["id"]: incident for incident in incidents}
        closed_incidents = [incident for incident in incidents if incident["status"] == "CLOSED"]
        active_incidents = [incident for incident in incidents if incident["status"] != "CLOSED"]
        event_incident_ids = {event["incident_id"] for event in events}
        restored_count = len([incident for incident in closed_incidents if incident["restored_at"] is not None])
        status_counts: dict[str, int] = {}
        attempt_count = 0
        for delivery in deliveries:
            status_counts[delivery["status"]] = status_counts.get(delivery["status"], 0) + 1
            attempt_count += len(self.list_webhook_attempts(delivery["event_id"]))

        total_incidents = len(incidents)
        closed_count = len(closed_incidents)
        audit_completeness_rate = round(len(event_incident_ids) / total_incidents, 3) if total_incidents else 0.0
        ground_truth_coverage = round(restored_count / closed_count, 3) if closed_count else 0.0

        stage_labels = {
            "INCIDENT_CREATED": "Incident opened",
            "ETA_REVISED": "ETA revised",
            "TIMEOUT_APPLIED": "Timeout failsafe",
            "INCIDENT_CLOSED": "Restoration closed loop",
        }
        journey = []
        for event in events[-8:]:
            incident = incidents_by_id.get(event["incident_id"], {})
            journey.append(
                {
                    "stage": stage_labels.get(event["event_type"], event["event_type"].replace("_", " ").title()),
                    "event_type": event["event_type"],
                    "partner_id": incident.get("partner_id", "synthetic-partner"),
                    "site_id": incident.get("site_id", "synthetic-site"),
                    "status": incident.get("status", "UNKNOWN"),
                    "reason_code": event["reason_code"],
                    "eta_hours": event["new_eta_hours"],
                    "occurred_at": dtstr(event["created_at"]),
                }
            )

        decision_rationale = []
        for incident in incidents[:5]:
            decision = self.decision_for_incident(incident)
            decision_rationale.append(
                {
                    "incident_id": incident["id"],
                    "partner_id": incident["partner_id"],
                    "site_id": incident["site_id"],
                    "status": incident["status"],
                    "eta_hours": decision["eta_hours"],
                    "confidence_band": decision["confidence_band"],
                    "reason_code": decision["reason_code"],
                    "partner_action": decision["partner_action"],
                    "policy_explanation": decision["policy_explanation"],
                }
            )

        recent_deliveries = [
            {
                "event_id": delivery["event_id"],
                "event_type": delivery["event_type"],
                "partner_id": delivery["partner_id"],
                "incident_id": delivery["incident_id"],
                "status": delivery["status"],
                "attempt_count": delivery["attempt_count"],
                "max_attempts": delivery["max_attempts"],
            }
            for delivery in deliveries[-6:]
        ]

        return {
            "generated_at": utcnow(),
            "data_boundary": "synthetic-public-safe",
            "narrative": "A 3-minute executive walkthrough from outage event to partner action and ML-ready ground truth.",
            "metrics": {
                "partner_profiles": len(profiles),
                "total_incidents": total_incidents,
                "active_incidents": len(active_incidents),
                "closed_incidents": closed_count,
                "timeout_fallbacks": len([incident for incident in incidents if incident["timeout_applied"]]),
                "audit_events": len(events),
                "webhook_deliveries": len(deliveries),
                "webhook_attempts": attempt_count,
                "audit_completeness_rate": audit_completeness_rate,
            },
            "partner_journey": journey,
            "decision_rationale": decision_rationale,
            "webhook_delivery": {
                "status_counts": status_counts,
                "recent_events": recent_deliveries,
                "private_delivery_headers": "excluded",
            },
            "ml_readiness": {
                "closed_dataset_rows": len(closed_dataset),
                "restoration_ground_truth_coverage": ground_truth_coverage,
                "export_shape": [
                    "prediction_time",
                    "actual_restoration_duration_hours",
                    "eta_error_hours",
                    "rule_version",
                    "feature_snapshot",
                ],
            },
            "public_safe_controls": [
                "Synthetic partner and site identifiers only",
                "Private delivery headers are excluded",
                "No real topology, endpoint, or field transcript is rendered",
            ],
        }

    def operator_console_summary(self) -> JSONDict:
        incidents = self.list_incidents()
        deliveries = self.list_webhook_deliveries()
        profiles = self.list_partner_profiles()
        closed_dataset = self.export_closed_incidents_dataset()
        now = utcnow()

        active_incidents = [incident for incident in incidents if incident["status"] != "CLOSED"]
        active_cards = []
        timeout_cards = []
        partner_action_cards = []
        for incident in active_incidents:
            decision = self.decision_for_incident(incident)
            reference_time = incident["last_signal_at"] or incident["created_at"]
            minutes_since_update = round((now - reference_time).total_seconds() / 60.0, 1)
            timeout_status = "applied" if incident["timeout_applied"] else "watch"
            if not incident["timeout_applied"] and minutes_since_update >= TIMEOUT_MINUTES * 0.75:
                timeout_status = "high"
            elif not incident["timeout_applied"] and minutes_since_update < TIMEOUT_MINUTES * 0.75:
                timeout_status = "normal"

            incident_card = {
                "incident_id": incident["id"],
                "partner_id": incident["partner_id"],
                "site_id": incident["site_id"],
                "status": incident["status"],
                "eta_hours": incident["current_eta_hours"],
                "reason_code": incident["reason_code"],
                "confidence_band": decision["confidence_band"],
                "partner_action": decision["partner_action"],
                "minutes_since_update": minutes_since_update,
            }
            active_cards.append(incident_card)
            partner_action_cards.append(
                {
                    "incident_id": incident["id"],
                    "site_id": incident["site_id"],
                    "recommendation": decision["recommendation"],
                    "partner_action": decision["partner_action"],
                    "policy_explanation": decision["policy_explanation"],
                }
            )
            if timeout_status != "normal":
                timeout_cards.append(
                    {
                        "incident_id": incident["id"],
                        "site_id": incident["site_id"],
                        "risk_level": timeout_status,
                        "minutes_since_update": minutes_since_update,
                        "timeout_minutes": TIMEOUT_MINUTES,
                        "current_eta_hours": incident["current_eta_hours"],
                        "reason_code": incident["reason_code"],
                    }
                )

        actionable_deliveries = [
            delivery
            for delivery in deliveries
            if delivery["status"] in {"queued", "retry_scheduled", "failed", "exhausted"}
        ]
        webhook_queue = [
            {
                "event_id": delivery["event_id"],
                "event_type": delivery["event_type"],
                "partner_id": delivery["partner_id"],
                "incident_id": delivery["incident_id"],
                "status": delivery["status"],
                "attempt_count": delivery["attempt_count"],
                "max_attempts": delivery["max_attempts"],
                "next_attempt_at": dtstr(delivery["next_attempt_at"]),
            }
            for delivery in actionable_deliveries[-8:]
        ]

        closed_incidents = [incident for incident in incidents if incident["status"] == "CLOSED"]
        restored_count = len([incident for incident in closed_incidents if incident["restored_at"] is not None])
        ground_truth_coverage = round(restored_count / len(closed_incidents), 3) if closed_incidents else 0.0

        return {
            "generated_at": now,
            "data_boundary": "synthetic-public-safe",
            "operating_questions": [
                "Which incidents need partner action now?",
                "Which incidents are near timeout fallback?",
                "Which webhook notifications still need delivery attention?",
                "Is closed-loop ground truth ready for evaluation?",
            ],
            "metrics": {
                "active_incidents": len(active_incidents),
                "timeout_risk_items": len(timeout_cards),
                "webhook_queue_items": len(webhook_queue),
                "closed_loop_rows": len(closed_dataset),
                "partner_profiles": len(profiles),
            },
            "active_incidents": active_cards,
            "timeout_risk": timeout_cards,
            "webhook_queue": webhook_queue,
            "partner_actions": partner_action_cards,
            "closed_loop_data": {
                "closed_incidents": len(closed_incidents),
                "dataset_rows": len(closed_dataset),
                "restoration_ground_truth_coverage": ground_truth_coverage,
                "next_metric_to_watch": "ETA error and underestimation rate by partner class",
            },
            "partner_scope_status": [
                {
                    "partner_id": profile["partner_id"],
                    "partner_class": profile["partner_class"],
                    "allowed_site_prefixes": profile["allowed_site_prefixes"],
                    "webhook_mode": profile["webhook_mode"],
                }
                for profile in profiles
            ],
            "public_safe_controls": [
                "Raw webhook headers are excluded",
                "Raw field signal text is excluded",
                "Only synthetic partner, site, and incident identifiers are rendered",
            ],
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

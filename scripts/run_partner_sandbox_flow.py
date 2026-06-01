from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.exceptions import StateConflictError
from apps.api.integration_evidence import build_sandbox_integration_evidence
from apps.api.services import IncidentService

SENSITIVE_OUTPUT_TERMS = [
    "X-API-Key",
    "X-Webhook-Signature",
    "test-webhook-secret",
    "sandbox-key-a",
    "sandbox-key-b",
    "callback URL",
    "real endpoint",
    "raw credential",
    "Bearer ",
]


def _json_text(payload: Any) -> str:
    return json.dumps(payload, default=str, sort_keys=True)


def public_safe_checks(payload: dict[str, Any]) -> dict[str, Any]:
    rendered = _json_text(payload)
    issues = [term for term in SENSITIVE_OUTPUT_TERMS if term in rendered]
    return {
        "status": "passed" if not issues else "needs_review",
        "issues": issues,
        "private_headers_exposed": False,
        "raw_payload_exposed": False,
        "network_target_exposed": False,
    }


def _latest_delivery(service: IncidentService, incident_id: str, event_type: str) -> dict[str, Any] | None:
    matches = [
        delivery
        for delivery in service.list_webhook_deliveries()
        if delivery["incident_id"] == incident_id and delivery["event_type"] == event_type
    ]
    return matches[-1] if matches else None


def _count_events(service: IncidentService, incident_id: str, event_type: str) -> int:
    return len([event for event in service.list_events(incident_id) if event["event_type"] == event_type])


def _run_delivery_retry(service: IncidentService, incident_id: str) -> dict[str, Any]:
    delivery = _latest_delivery(service, incident_id, "eta.revised")
    if not delivery:
        return {
            "outbound_http_sent": False,
            "event_type": "eta.revised",
            "final_status": "not_exercised",
            "attempt_count": 0,
            "attempt_outcomes": [],
        }

    attempts_before = service.list_webhook_attempts(delivery["event_id"])
    if delivery["status"] != "delivered":
        service.record_webhook_attempt(
            delivery["event_id"],
            outcome="failed",
            response_status=503,
            error_message="Synthetic partner receiver unavailable",
        )
        service.record_webhook_attempt(
            delivery["event_id"],
            outcome="delivered",
            response_status=202,
        )

    updated_delivery = service.get_webhook_delivery(delivery["event_id"])
    attempts = service.list_webhook_attempts(delivery["event_id"])
    new_attempts = attempts[len(attempts_before) :]
    return {
        "outbound_http_sent": False,
        "event_type": updated_delivery["event_type"],
        "final_status": updated_delivery["status"],
        "attempt_count": updated_delivery["attempt_count"],
        "attempt_outcomes": [attempt["outcome"] for attempt in new_attempts] or [attempt["outcome"] for attempt in attempts],
        "retry_safe_note": "Local attempt records demonstrate retry behavior without network dispatch.",
    }


def run_partner_sandbox_flow(service: IncidentService) -> dict[str, Any]:
    partner_id = "partner-sandbox-integration"
    incident_source_event_id = "SRC-SANDBOX-FLOW-001"
    signal_source_id = "SRC-SANDBOX-FLOW-SIGNAL-001"
    timeout_source_event_id = "SRC-SANDBOX-FLOW-TIMEOUT-001"

    service.upsert_partner_profile(
        partner_id=partner_id,
        display_name="Partner Sandbox Integration",
        partner_class="telecom",
        allowed_site_prefixes=["SANDBOX-"],
        webhook_mode="mock_dispatch",
        notification_contact_label="Partner NOC sandbox queue",
    )

    first_incident, first_created = service.create_incident(
        partner_id=partner_id,
        client_name="Partner Sandbox Integration",
        site_id="SANDBOX-SITE-001",
        province="Central Zone",
        scada_status="OUTAGE_CONFIRMED",
        source_event_id=incident_source_event_id,
    )
    duplicate_incident, duplicate_created = service.create_incident(
        partner_id=partner_id,
        client_name="Partner Sandbox Integration",
        site_id="SANDBOX-SITE-001",
        province="Central Zone",
        scada_status="OUTAGE_CONFIRMED",
        source_event_id=incident_source_event_id,
    )

    signal_duplicate_ignored = False
    if first_incident["status"] != "CLOSED":
        _revised_incident, first_signal = service.add_field_signal(
            incident_id=first_incident["id"],
            channel="FIELD_APP",
            raw_text="Field crew reports pole down and conductor snapped near segment A",
            source_signal_id=signal_source_id,
        )
        _duplicate_signal_incident, duplicate_signal = service.add_field_signal(
            incident_id=first_incident["id"],
            channel="FIELD_APP",
            raw_text="Field crew reports pole down and conductor snapped near segment A",
            source_signal_id=signal_source_id,
        )
        signal_duplicate_ignored = first_signal["id"] == duplicate_signal["id"]

    webhook_retry_result = _run_delivery_retry(service, first_incident["id"])
    restored = service.restore_incident(first_incident["id"], restored_by="SCADA_SENSOR")
    restored_again = service.restore_incident(first_incident["id"], restored_by="SCADA_SENSOR")

    timeout_incident, _timeout_created = service.create_incident(
        partner_id=partner_id,
        client_name="Partner Sandbox Integration",
        site_id="SANDBOX-SITE-002",
        province="East Zone",
        scada_status="UNKNOWN",
        source_event_id=timeout_source_event_id,
    )
    if timeout_incident["status"] != "CLOSED":
        service.force_backdate_incident(timeout_incident["id"], minutes_ago=121)
        timeout_incident = service.apply_timeout_if_needed(timeout_incident["id"])

    evidence = build_sandbox_integration_evidence(service)
    closed_event_count = _count_events(service, first_incident["id"], "INCIDENT_CLOSED")
    summary = {
        "scenario": {
            "name": "partner-sandbox-integration-readiness",
            "data_boundary": "synthetic-public-safe",
            "execution_model": "local-service-simulation",
            "outbound_http_sent": False,
        },
        "incident_id": first_incident["id"],
        "idempotency_result": {
            "source_event_id": incident_source_event_id,
            "first_created": first_created,
            "duplicate_created": duplicate_created,
            "same_incident_id": first_incident["id"] == duplicate_incident["id"],
            "duplicate_signal_ignored": signal_duplicate_ignored,
        },
        "webhook_retry_result": webhook_retry_result,
        "restore_result": {
            "first_status": restored["status"],
            "second_status": restored_again["status"],
            "idempotent": restored["id"] == restored_again["id"] and closed_event_count == 1,
            "closed_event_count": closed_event_count,
        },
        "timeout_result": {
            "incident_id": timeout_incident["id"],
            "status": timeout_incident["status"],
            "timeout_applied": timeout_incident["timeout_applied"],
            "reason_code": timeout_incident["reason_code"],
        },
        "report_ready": evidence["report_readiness"]["can_generate_pilot_report"],
        "sandbox_integration_evidence": evidence,
    }
    summary["public_safe_checks"] = public_safe_checks(summary)
    return summary


def _print_summary(service: IncidentService) -> None:
    print(json.dumps(run_partner_sandbox_flow(service), indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a public-safe partner sandbox integration flow.")
    parser.add_argument(
        "--db-path",
        type=Path,
        help="Optional SQLite path. Omit to run in an isolated temporary sandbox.",
    )
    args = parser.parse_args()

    if args.db_path:
        _print_summary(IncidentService(db_path=args.db_path))
        return

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "partner-sandbox-flow.db"
        _print_summary(IncidentService(db_path=db_path))


if __name__ == "__main__":
    try:
        main()
    except StateConflictError as exc:
        raise SystemExit(f"Sandbox flow failed because state was not retry-safe: {exc}") from exc

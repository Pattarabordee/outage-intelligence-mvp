from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .services import IncidentService

JSONDict = dict[str, Any]


def _rate(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def build_sandbox_integration_evidence(service: IncidentService) -> JSONDict:
    """Summarize whether the local sandbox has exercised partner integration paths."""
    profiles = service.list_partner_profiles()
    incidents = service.list_incidents()
    events = service.list_all_events()
    deliveries = service.list_webhook_deliveries()
    closed_rows = service.export_closed_incidents_dataset()

    event_counts = Counter(event["event_type"] for event in events)
    delivery_counts = Counter(delivery["event_type"] for delivery in deliveries)
    delivery_status_counts = Counter(delivery["status"] for delivery in deliveries)
    attempted_records = [delivery for delivery in deliveries if delivery["attempt_count"] > 0]
    delivered_records = [delivery for delivery in deliveries if delivery["status"] == "delivered"]
    attempt_total = sum(len(service.list_webhook_attempts(delivery["event_id"])) for delivery in deliveries)

    flow_status = {
        "partner_profile_configured": bool(profiles),
        "incident_create_covered": event_counts["INCIDENT_CREATED"] > 0 or delivery_counts["incident.created"] > 0,
        "eta_revision_covered": event_counts["ETA_REVISED"] > 0 or delivery_counts["eta.revised"] > 0,
        "timeout_failsafe_covered": event_counts["TIMEOUT_APPLIED"] > 0 or delivery_counts["timeout.applied"] > 0,
        "restoration_closed_loop_covered": event_counts["INCIDENT_CLOSED"] > 0
        or delivery_counts["incident.restored"] > 0,
        "duplicate_event_covered": delivery_counts["duplicate.ignored"] > 0,
    }

    covered_steps = sum(1 for value in flow_status.values() if value)
    return {
        "mode": "local-outbox-only",
        "outbound_http_sent": False,
        "flow_status": flow_status,
        "flow_coverage_rate": _rate(covered_steps, len(flow_status)),
        "retry_behavior": {
            "delivery_records": len(deliveries),
            "attempted_records": len(attempted_records),
            "delivered_records": len(delivered_records),
            "attempt_records": attempt_total,
            "delivery_rate": _rate(len(delivered_records), len(deliveries)),
            "attempt_rate": _rate(len(attempted_records), len(deliveries)),
            "status_counts": dict(delivery_status_counts),
            "event_id_dedup_expected": True,
        },
        "idempotency_controls": [
            "source_event_id",
            "idempotency_key",
            "source_signal_id",
            "event_id",
        ],
        "report_readiness": {
            "incidents": len(incidents),
            "closed_loop_rows": len(closed_rows),
            "can_generate_pilot_report": bool(closed_rows and deliveries),
        },
        "private_pilot_gaps": [
            "Production authorization policy",
            "Managed delivery worker",
            "Receiver-side verification",
            "Replay window enforcement",
            "Live telemetry and alert routing",
        ],
    }

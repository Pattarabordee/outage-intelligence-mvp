from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.services import IncidentService


def main() -> None:
    service = IncidentService()
    partner_id = "partner-telecom-sandbox"
    service.upsert_partner_profile(
        partner_id=partner_id,
        display_name="Telecom Sandbox Partner",
        partner_class="telecom",
        allowed_site_prefixes=["TEL-"],
        webhook_mode="mock_dispatch",
        notification_contact_label="Partner NOC sandbox queue",
    )

    incident, _created = service.create_incident(
        partner_id=partner_id,
        client_name="Telecom Sandbox Partner",
        site_id="TEL-SITE-DEMO-001",
        province="Central Zone",
        scada_status="OUTAGE_CONFIRMED",
        source_event_id="SRC-DEMO-INCIDENT-001",
    )
    service.add_field_signal(
        incident_id=incident["id"],
        channel="FIELD_APP",
        raw_text="Field crew reports pole down and conductor snapped near segment A",
        source_signal_id="SRC-DEMO-SIGNAL-001",
    )
    eta_delivery = next(
        delivery
        for delivery in service.list_webhook_deliveries(partner_id=partner_id)
        if delivery["incident_id"] == incident["id"] and delivery["event_type"] == "eta.revised"
    )
    if eta_delivery["status"] != "delivered":
        service.record_webhook_attempt(
            eta_delivery["event_id"],
            outcome="failed",
            response_status=503,
            error_message="Synthetic partner receiver unavailable",
        )
        service.record_webhook_attempt(
            eta_delivery["event_id"],
            outcome="delivered",
            response_status=202,
        )
    service.restore_incident(incident["id"], restored_by="SCADA_SENSOR")

    timeout_incident, _created = service.create_incident(
        partner_id=partner_id,
        client_name="Telecom Sandbox Partner",
        site_id="TEL-SITE-DEMO-002",
        province="East Zone",
        scada_status="UNKNOWN",
        source_event_id="SRC-DEMO-INCIDENT-002",
    )
    service.force_backdate_incident(timeout_incident["id"], minutes_ago=121)
    service.apply_timeout_if_needed(timeout_incident["id"])

    summary = service.executive_summary()
    print(f"Seeded executive demo incidents: {summary['metrics']['total_incidents']}")
    print(f"Webhook deliveries: {summary['metrics']['webhook_deliveries']}")
    print(f"Closed-loop rows: {summary['ml_readiness']['closed_dataset_rows']}")


if __name__ == "__main__":
    main()

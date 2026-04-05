from __future__ import annotations

from apps.api.services import IncidentService


def main() -> None:
    service = IncidentService()
    incident = service.create_incident(
        client_name="DemoOperator",
        site_id="SITE-DEMO-001",
        province="Central Zone",
        scada_status="OUTAGE_CONFIRMED",
    )
    service.add_field_signal(
        incident_id=incident["id"],
        channel="FIELD_APP",
        raw_text="Patrol underway. Fault not located yet.",
    )
    print(f"Seeded incident: {incident['id']}")


if __name__ == "__main__":
    main()

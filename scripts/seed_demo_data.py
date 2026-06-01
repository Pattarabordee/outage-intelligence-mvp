from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.services import IncidentService


def main() -> None:
    service = IncidentService()
    incident, _created = service.create_incident(
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

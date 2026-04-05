from __future__ import annotations

import os
import tempfile
from pprint import pprint

from fastapi.testclient import TestClient

from .main import create_app


def main() -> None:
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        app = create_app(db_path=db_path)
        client = TestClient(app)

        create_res = client.post(
            "/api/v1/incidents",
            json={
                "client_name": "DemoOperator",
                "site_id": "SITE-1001",
                "province": "North Zone",
                "scada_status": "OUTAGE_CONFIRMED",
            },
        )
        create_payload = create_res.json()
        incident_id = create_payload["incident"]["id"]
        print("\n1) Immediate Hold Response")
        pprint(create_payload)

        signal_res = client.post(
            f"/api/v1/incidents/{incident_id}/signals/field",
            json={
                "channel": "FIELD_APP",
                "raw_text": "Field crew reports pole down and conductor snapped near segment A",
            },
        )
        print("\n2) Field Signal Revised ETA")
        pprint(signal_res.json())

        restore_res = client.post(
            f"/api/v1/incidents/{incident_id}/restore",
            json={"restored_by": "SCADA_SENSOR"},
        )
        print("\n3) Restoration Closed Loop")
        pprint(restore_res.json())
    finally:
        client.close()


if __name__ == "__main__":
    main()

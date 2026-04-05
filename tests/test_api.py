from __future__ import annotations

import os
import tempfile

from fastapi.testclient import TestClient

from apps.api.main import create_app


def make_client():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    app = create_app(db_path=db_path)
    return TestClient(app), db_path


def test_create_incident_and_revise_eta():
    client, tmp = make_client()
    try:
        create_res = client.post(
            "/api/v1/incidents",
            json={
                "client_name": "DemoOperator",
                "site_id": "SITE-1001",
                "province": "North Zone",
                "scada_status": "OUTAGE_CONFIRMED",
            },
        )
        assert create_res.status_code == 200
        payload = create_res.json()
        incident_id = payload["incident"]["id"]
        assert payload["incident"]["current_eta_hours"] == 2.0

        signal_res = client.post(
            f"/api/v1/incidents/{incident_id}/signals/field",
            json={
                "channel": "FIELD_APP",
                "raw_text": "Pole down and conductor snapped near segment A",
            },
        )
        assert signal_res.status_code == 200
        signal_payload = signal_res.json()
        assert signal_payload["incident"]["current_eta_hours"] == 7.0
        assert signal_payload["incident"]["reason_code"] in {"STRUCTURAL_DAMAGE", "BROKEN_CONDUCTOR"}
    finally:
        client.close()


def test_timeout_worst_case_path():
    client, tmp = make_client()
    try:
        create_res = client.post(
            "/api/v1/incidents",
            json={
                "client_name": "DemoOperator",
                "site_id": "SITE-2001",
                "province": "East Zone",
                "scada_status": "UNKNOWN",
            },
        )
        incident_id = create_res.json()["incident"]["id"]

        # This test-only helper is intentionally not exposed through the public API surface.
        app = client.app
        app.state.service.force_backdate_incident(incident_id, minutes_ago=121)

        timeout_res = client.post(f"/api/v1/incidents/{incident_id}/timeout-check")
        assert timeout_res.status_code == 200
        payload = timeout_res.json()
        assert payload["timeout_applied"] is True
        assert payload["current_eta_hours"] == 8.0
        assert payload["reason_code"] == "TIMEOUT_FAILSAFE"
    finally:
        client.close()


def test_restore_closes_ticket():
    client, tmp = make_client()
    try:
        create_res = client.post(
            "/api/v1/incidents",
            json={
                "client_name": "DemoOperator",
                "site_id": "SITE-3001",
                "province": "South Zone",
                "scada_status": "OUTAGE_CONFIRMED",
            },
        )
        incident_id = create_res.json()["incident"]["id"]
        restore_res = client.post(
            f"/api/v1/incidents/{incident_id}/restore",
            json={"restored_by": "SCADA_SENSOR"},
        )
        assert restore_res.status_code == 200
        payload = restore_res.json()
        assert payload["status"] == "CLOSED"
        assert payload["severity"] == "resolved"
        assert payload["current_eta_hours"] == 0.0
    finally:
        client.close()

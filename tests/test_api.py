from __future__ import annotations

def create_incident(client, site_id: str = "SITE-1001", headers: dict | None = None, **overrides):
    payload = {
        "client_name": "DemoEnterprisePartner",
        "site_id": site_id,
        "province": "North Zone",
        "scada_status": "OUTAGE_CONFIRMED",
    }
    payload.update(overrides)
    return client.post("/api/v1/incidents", json=payload, headers=headers)


def test_create_incident_and_revise_eta(client):
    create_res = create_incident(client)
    assert create_res.status_code == 201
    assert create_res.headers["location"].startswith("/api/v1/incidents/")
    payload = create_res.json()
    incident_id = payload["incident"]["id"]
    assert payload["incident"]["current_eta_hours"] == 2.0
    assert payload["decision"]["policy_version"] == "rules-v1"
    assert payload["decision"]["partner_action"].startswith("Wait")
    assert payload["decision"]["sla_behavior"]["timeout_minutes"] == 120
    assert "source_event_id" in payload["decision"]["sla_behavior"]["idempotency_fields"]

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
    assert signal_payload["decision"]["partner_action"].startswith("Activate")
    assert "prolonged outage risk" in signal_payload["decision"]["policy_explanation"]
    assert signal_payload["events"][-1]["event_type"] == "ETA_REVISED"


def test_timeout_worst_case_path(client):
    create_res = create_incident(client, site_id="SITE-2001", province="East Zone", scada_status="UNKNOWN")
    incident_id = create_res.json()["incident"]["id"]

    # This test-only helper is intentionally not exposed through the public API surface.
    client.app.state.service.force_backdate_incident(incident_id, minutes_ago=121)

    timeout_res = client.post(f"/api/v1/incidents/{incident_id}/timeout-check")
    assert timeout_res.status_code == 200
    payload = timeout_res.json()
    assert payload["timeout_applied"] is True
    assert payload["current_eta_hours"] == 8.0
    assert payload["reason_code"] == "TIMEOUT_FAILSAFE"

    second_timeout_res = client.post(f"/api/v1/incidents/{incident_id}/timeout-check")
    assert second_timeout_res.status_code == 200
    incident_res = client.get(f"/api/v1/incidents/{incident_id}")
    timeout_events = [event for event in incident_res.json()["events"] if event["event_type"] == "TIMEOUT_APPLIED"]
    assert len(timeout_events) == 1


def test_health_endpoint_declares_public_safe_enterprise_service(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "enterprise-outage-intelligence",
        "version": "0.2.0",
        "data_boundary": "synthetic-public-safe",
        "sandbox_auth": "disabled",
    }


def test_ready_endpoint_reports_pilot_readiness_checks(client):
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"]["incident_store"] == "ok"


def test_sandbox_auth_requires_valid_partner_key(auth_client, partner_a_headers):
    missing_res = auth_client.post(
        "/api/v1/incidents",
        json={
            "client_name": "DemoEnterprisePartner",
            "site_id": "SITE-AUTH-001",
            "province": "North Zone",
            "scada_status": "OUTAGE_CONFIRMED",
        },
    )
    invalid_res = auth_client.post(
        "/api/v1/incidents",
        headers={"X-Partner-Id": "partner-a", "X-API-Key": "wrong-key"},
        json={
            "client_name": "DemoEnterprisePartner",
            "site_id": "SITE-AUTH-002",
            "province": "North Zone",
            "scada_status": "OUTAGE_CONFIRMED",
        },
    )
    valid_res = create_incident(auth_client, site_id="SITE-AUTH-003", headers=partner_a_headers)

    assert missing_res.status_code == 401
    assert missing_res.json()["error"]["code"] == "unauthorized"
    assert invalid_res.status_code == 401
    assert invalid_res.json()["error"]["code"] == "unauthorized"
    assert valid_res.status_code == 201
    assert valid_res.json()["incident"]["partner_id"] == "partner-a"


def test_partner_cannot_access_another_partner_incident(auth_client, partner_a_headers, partner_b_headers):
    create_res = create_incident(auth_client, site_id="SITE-TENANT-001", headers=partner_a_headers)
    incident_id = create_res.json()["incident"]["id"]

    forbidden_res = auth_client.get(f"/api/v1/incidents/{incident_id}", headers=partner_b_headers)

    assert forbidden_res.status_code == 403
    assert forbidden_res.json()["error"]["code"] == "forbidden"


def test_partner_id_must_match_authenticated_context(auth_client, partner_a_headers):
    response = create_incident(
        auth_client,
        site_id="SITE-TENANT-002",
        headers=partner_a_headers,
        partner_id="partner-b",
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_source_event_id_is_idempotent_per_partner(auth_client, partner_a_headers, partner_b_headers):
    payload = {
        "client_name": "DemoEnterprisePartner",
        "site_id": "SITE-TENANT-003",
        "province": "North Zone",
        "scada_status": "OUTAGE_CONFIRMED",
        "source_event_id": "SRC-SHARED-001",
    }

    first_res = auth_client.post("/api/v1/incidents", json=payload, headers=partner_a_headers)
    duplicate_res = auth_client.post("/api/v1/incidents", json=payload, headers=partner_a_headers)
    other_partner_res = auth_client.post("/api/v1/incidents", json=payload, headers=partner_b_headers)

    assert first_res.status_code == 201
    assert duplicate_res.status_code == 200
    assert other_partner_res.status_code == 201
    assert first_res.json()["incident"]["id"] == duplicate_res.json()["incident"]["id"]
    assert first_res.json()["incident"]["id"] != other_partner_res.json()["incident"]["id"]


def test_restore_closes_ticket_and_exports_dataset(client):
    create_res = create_incident(client, site_id="SITE-3001", province="South Zone")
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

    dataset = client.app.state.service.export_closed_incidents_dataset()
    assert dataset[0]["incident_id"] == incident_id
    assert "eta_error_hours" in dataset[0]
    assert dataset[0]["rule_version"] == "rules-v1"
    assert dataset[0]["feature_snapshot"]["partner_id"] == "demo-enterprise-partner"

    second_restore_res = client.post(
        f"/api/v1/incidents/{incident_id}/restore",
        json={"restored_by": "SCADA_SENSOR"},
    )
    assert second_restore_res.status_code == 200
    assert second_restore_res.json()["id"] == incident_id


def test_duplicate_source_event_id_returns_existing_incident(client):
    payload = {
        "client_name": "DemoEnterprisePartner",
        "site_id": "SITE-4001",
        "province": "North Zone",
        "scada_status": "OUTAGE_CONFIRMED",
        "source_event_id": "SRC-EVENT-4001",
    }
    first_res = client.post("/api/v1/incidents", json=payload)
    second_res = client.post("/api/v1/incidents", json=payload)

    assert first_res.status_code == 201
    assert second_res.status_code == 200
    assert first_res.json()["incident"]["id"] == second_res.json()["incident"]["id"]


def test_duplicate_source_signal_id_returns_existing_signal(client):
    create_res = create_incident(client, site_id="SITE-4501")
    incident_id = create_res.json()["incident"]["id"]
    payload = {
        "channel": "FIELD_APP",
        "raw_text": "Patrol underway. Fault not located yet.",
        "source_signal_id": "SRC-SIGNAL-4501",
    }

    first_res = client.post(f"/api/v1/incidents/{incident_id}/signals/field", json=payload)
    second_res = client.post(f"/api/v1/incidents/{incident_id}/signals/field", json=payload)

    assert first_res.status_code == 200
    assert second_res.status_code == 200
    assert first_res.json()["signals"][0]["id"] == second_res.json()["signals"][0]["id"]


def test_signal_after_closed_incident_is_rejected(client):
    create_res = create_incident(client, site_id="SITE-5001")
    incident_id = create_res.json()["incident"]["id"]
    client.post(f"/api/v1/incidents/{incident_id}/restore", json={"restored_by": "SCADA_SENSOR"})

    signal_res = client.post(
        f"/api/v1/incidents/{incident_id}/signals/field",
        json={"channel": "FIELD_APP", "raw_text": "Patrol underway."},
    )

    assert signal_res.status_code == 409
    assert signal_res.json()["error"]["code"] == "state_conflict"


def test_restoration_field_signal_is_persisted_in_audit_trail(client):
    create_res = create_incident(client, site_id="SITE-6001")
    incident_id = create_res.json()["incident"]["id"]

    signal_res = client.post(
        f"/api/v1/incidents/{incident_id}/signals/field",
        json={
            "channel": "FIELD_APP",
            "raw_text": "Power restored and load normalized",
            "source_signal_id": "SRC-SIGNAL-6001",
        },
    )

    payload = signal_res.json()
    assert payload["incident"]["status"] == "CLOSED"
    assert payload["signals"][0]["source_signal_id"] == "SRC-SIGNAL-6001"
    assert payload["events"][-1]["event_type"] == "INCIDENT_CLOSED"


def test_unknown_incident_and_invalid_payload_use_standard_error_shape(client):
    missing_res = client.get("/api/v1/incidents/INC-NOTFOUND")
    invalid_res = client.post(
        "/api/v1/incidents/INC-NOTFOUND/signals/field",
        json={"channel": "FIELD_APP", "raw_text": ""},
    )

    assert missing_res.status_code == 404
    assert missing_res.json()["error"]["code"] == "not_found"
    assert invalid_res.status_code == 422
    assert invalid_res.json()["error"]["code"] == "validation_error"


def test_unknown_text_and_multiple_keyword_conflict_resolution(client):
    create_res = create_incident(client, site_id="SITE-7001")
    incident_id = create_res.json()["incident"]["id"]

    unknown_res = client.post(
        f"/api/v1/incidents/{incident_id}/signals/field",
        json={"channel": "FIELD_APP", "raw_text": "Crew is checking the area"},
    )
    assert unknown_res.json()["incident"]["reason_code"] == "UNCLASSIFIED_FIELD_SIGNAL"
    assert unknown_res.json()["incident"]["current_eta_hours"] == 4.0

    conflict_res = client.post(
        f"/api/v1/incidents/{incident_id}/signals/field",
        json={"channel": "FIELD_APP", "raw_text": "Breaker trip and pole down near segment A"},
    )
    assert conflict_res.json()["incident"]["reason_code"] == "STRUCTURAL_DAMAGE"
    assert conflict_res.json()["incident"]["current_eta_hours"] == 7.0

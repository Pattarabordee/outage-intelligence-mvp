from __future__ import annotations

SENSITIVE_DEMO_TERMS = [
    "X-API-Key",
    "X-Webhook-Signature",
    "test-webhook-secret",
    "sandbox-key-a",
    "sandbox-key-b",
    "callback URL",
    "credential",
    "token",
    "real endpoint",
    "raw credential",
]


def create_incident(client, site_id: str = "SITE-1001", headers: dict | None = None, **overrides):
    payload = {
        "client_name": "DemoEnterprisePartner",
        "site_id": site_id,
        "province": "North Zone",
        "scada_status": "OUTAGE_CONFIRMED",
    }
    payload.update(overrides)
    return client.post("/api/v1/incidents", json=payload, headers=headers)


def seed_executive_demo_story(client, headers: dict | None = None):
    create_res = create_incident(
        client,
        site_id="SITE-DEMO-EXEC-001",
        headers=headers,
        source_event_id="SRC-DEMO-EXEC-001",
    )
    incident_id = create_res.json()["incident"]["id"]
    client.post(
        f"/api/v1/incidents/{incident_id}/signals/field",
        headers=headers,
        json={
            "channel": "FIELD_APP",
            "raw_text": "Pole down and conductor snapped near segment A",
            "source_signal_id": "SRC-DEMO-EXEC-SIGNAL-001",
        },
    )
    deliveries = client.get("/api/v1/webhook-deliveries", headers=headers).json()
    eta_delivery = next(
        delivery
        for delivery in deliveries
        if delivery["incident_id"] == incident_id and delivery["event_type"] == "eta.revised"
    )
    client.post(
        f"/api/v1/webhook-deliveries/{eta_delivery['event_id']}/attempts",
        headers=headers,
        json={"outcome": "failed", "response_status": 503, "error_message": "Synthetic partner receiver unavailable"},
    )
    client.post(
        f"/api/v1/webhook-deliveries/{eta_delivery['event_id']}/attempts",
        headers=headers,
        json={"outcome": "delivered", "response_status": 202},
    )
    client.post(f"/api/v1/incidents/{incident_id}/restore", headers=headers, json={"restored_by": "SCADA_SENSOR"})

    active_res = create_incident(
        client,
        site_id="SITE-DEMO-EXEC-003",
        headers=headers,
        scada_status="OUTAGE_CONFIRMED",
        source_event_id="SRC-DEMO-EXEC-003",
    )
    active_id = active_res.json()["incident"]["id"]
    client.post(
        f"/api/v1/incidents/{active_id}/signals/field",
        headers=headers,
        json={
            "channel": "FIELD_APP",
            "raw_text": "Patrol underway. Fault not located yet.",
            "source_signal_id": "SRC-DEMO-EXEC-SIGNAL-003",
        },
    )

    timeout_res = create_incident(
        client,
        site_id="SITE-DEMO-EXEC-002",
        headers=headers,
        scada_status="UNKNOWN",
        source_event_id="SRC-DEMO-EXEC-002",
    )
    timeout_id = timeout_res.json()["incident"]["id"]
    client.app.state.service.force_backdate_incident(timeout_id, minutes_ago=121)
    client.post(f"/api/v1/incidents/{timeout_id}/timeout-check", headers=headers)
    timeout_delivery = next(
        delivery
        for delivery in client.get("/api/v1/webhook-deliveries", headers=headers).json()
        if delivery["incident_id"] == timeout_id and delivery["event_type"] == "timeout.applied"
    )
    client.post(
        f"/api/v1/webhook-deliveries/{timeout_delivery['event_id']}/attempts",
        headers=headers,
        json={"outcome": "failed", "response_status": 503, "error_message": "Synthetic partner receiver unavailable"},
    )
    return incident_id


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


def test_executive_summary_endpoint_is_public_safe_and_story_ready(auth_client, partner_a_headers):
    seed_executive_demo_story(auth_client, headers=partner_a_headers)

    response = auth_client.get("/api/v1/demo/executive-summary")
    payload = response.json()
    response_text = response.text

    assert response.status_code == 200
    assert payload["data_boundary"] == "synthetic-public-safe"
    assert payload["metrics"]["total_incidents"] >= 2
    assert payload["metrics"]["webhook_attempts"] >= 2
    assert payload["webhook_delivery"]["status_counts"]["delivered"] >= 1
    assert payload["ml_readiness"]["closed_dataset_rows"] >= 1
    assert {"ETA_REVISED", "TIMEOUT_APPLIED", "INCIDENT_CLOSED"}.issubset(
        {item["event_type"] for item in payload["partner_journey"]}
    )
    for term in SENSITIVE_DEMO_TERMS:
        assert term not in response_text


def test_executive_demo_page_renders_sections_without_sensitive_values(auth_client, partner_a_headers):
    seed_executive_demo_story(auth_client, headers=partner_a_headers)

    response = auth_client.get("/demo/incidents")
    html = response.text

    assert response.status_code == 200
    for section in ["Executive Summary", "Partner Journey", "Decision Rationale", "Webhook Delivery", "ML Readiness"]:
        assert section in html
    assert "Skip to main content" in html
    for term in SENSITIVE_DEMO_TERMS:
        assert term not in html


def test_operator_console_summary_is_public_safe_and_actionable(auth_client, partner_a_headers):
    seed_executive_demo_story(auth_client, headers=partner_a_headers)

    response = auth_client.get("/api/v1/operator/console-summary")
    payload = response.json()
    response_text = response.text

    assert response.status_code == 200
    assert payload["data_boundary"] == "synthetic-public-safe"
    assert payload["metrics"]["active_incidents"] >= 2
    assert payload["metrics"]["timeout_risk_items"] >= 1
    assert payload["metrics"]["webhook_queue_items"] >= 1
    assert payload["closed_loop_data"]["dataset_rows"] >= 1
    assert any(item["risk_level"] in {"applied", "high"} for item in payload["timeout_risk"])
    assert any(item["status"] in {"queued", "retry_scheduled"} for item in payload["webhook_queue"])
    assert payload["partner_actions"]
    for term in SENSITIVE_DEMO_TERMS:
        assert term not in response_text


def test_operator_console_page_renders_sections_without_sensitive_values(auth_client, partner_a_headers):
    seed_executive_demo_story(auth_client, headers=partner_a_headers)

    response = auth_client.get("/demo/operator-console")
    html = response.text

    assert response.status_code == 200
    for section in ["Active Incidents", "Timeout Risk", "Webhook Queue", "Partner Actions", "Closed-loop Data"]:
        assert section in html
    assert "Skip to main content" in html
    for term in SENSITIVE_DEMO_TERMS:
        assert term not in html


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


def test_partner_profile_controls_sandbox_site_scope(auth_client, partner_a_headers, partner_b_headers):
    profile_res = auth_client.put(
        "/api/v1/partners/partner-a/sandbox-profile",
        headers=partner_a_headers,
        json={
            "display_name": "Telecom Sandbox Partner",
            "partner_class": "telecom",
            "allowed_site_prefixes": ["TEL-"],
            "webhook_mode": "mock_dispatch",
            "notification_contact_label": "Partner NOC sandbox queue",
        },
    )
    forbidden_profile_res = auth_client.get("/api/v1/partners/partner-a/sandbox-profile", headers=partner_b_headers)
    denied_incident_res = create_incident(auth_client, site_id="SITE-OUTSIDE-001", headers=partner_a_headers)
    allowed_incident_res = create_incident(auth_client, site_id="TEL-SITE-001", headers=partner_a_headers)

    assert profile_res.status_code == 200
    assert profile_res.json()["partner_class"] == "telecom"
    assert profile_res.json()["webhook_mode"] == "mock_dispatch"
    assert forbidden_profile_res.status_code == 403
    assert denied_incident_res.status_code == 403
    assert denied_incident_res.json()["error"]["code"] == "forbidden"
    assert allowed_incident_res.status_code == 201


def test_webhook_delivery_is_queued_signed_and_retryable(auth_client, partner_a_headers, partner_b_headers):
    create_res = create_incident(auth_client, site_id="SITE-WEBHOOK-001", headers=partner_a_headers)
    delivery_res = auth_client.get("/api/v1/webhook-deliveries", headers=partner_a_headers)

    assert create_res.status_code == 201
    assert delivery_res.status_code == 200
    delivery = delivery_res.json()[0]
    assert delivery["event_type"] == "incident.created"
    assert delivery["partner_id"] == "partner-a"
    assert delivery["headers"]["X-Webhook-Signature"].startswith("sha256=")
    assert delivery["payload"]["event_id"] == delivery["event_id"]
    assert delivery["status"] == "queued"

    forbidden_res = auth_client.get(f"/api/v1/webhook-deliveries/{delivery['event_id']}", headers=partner_b_headers)
    retry_res = auth_client.post(f"/api/v1/webhook-deliveries/{delivery['event_id']}/retry", headers=partner_a_headers)

    assert forbidden_res.status_code == 403
    assert retry_res.status_code == 200
    assert retry_res.json()["attempt_count"] == 1
    assert retry_res.json()["status"] == "retry_scheduled"
    assert retry_res.json()["next_attempt_at"] is not None


def test_webhook_delivery_attempts_update_sandbox_dispatch_state(auth_client, partner_a_headers, partner_b_headers):
    create_res = create_incident(auth_client, site_id="SITE-WEBHOOK-ATTEMPT-001", headers=partner_a_headers)
    delivery = auth_client.get("/api/v1/webhook-deliveries", headers=partner_a_headers).json()[0]

    forbidden_attempt_res = auth_client.post(
        f"/api/v1/webhook-deliveries/{delivery['event_id']}/attempts",
        headers=partner_b_headers,
        json={"outcome": "failed", "response_status": 503, "error_message": "Synthetic partner receiver unavailable"},
    )
    failed_attempt_res = auth_client.post(
        f"/api/v1/webhook-deliveries/{delivery['event_id']}/attempts",
        headers=partner_a_headers,
        json={"outcome": "failed", "response_status": 503, "error_message": "Synthetic partner receiver unavailable"},
    )
    delivered_attempt_res = auth_client.post(
        f"/api/v1/webhook-deliveries/{delivery['event_id']}/attempts",
        headers=partner_a_headers,
        json={"outcome": "delivered", "response_status": 202},
    )
    attempts_res = auth_client.get(f"/api/v1/webhook-deliveries/{delivery['event_id']}/attempts", headers=partner_a_headers)
    retry_after_delivered_res = auth_client.post(
        f"/api/v1/webhook-deliveries/{delivery['event_id']}/retry",
        headers=partner_a_headers,
    )

    assert create_res.status_code == 201
    assert forbidden_attempt_res.status_code == 403
    assert failed_attempt_res.status_code == 201
    assert failed_attempt_res.json()["delivery"]["status"] == "retry_scheduled"
    assert failed_attempt_res.json()["delivery"]["attempt_count"] == 1
    assert delivered_attempt_res.status_code == 201
    assert delivered_attempt_res.json()["delivery"]["status"] == "delivered"
    assert delivered_attempt_res.json()["attempt"]["attempt_number"] == 2
    assert attempts_res.status_code == 200
    assert [attempt["outcome"] for attempt in attempts_res.json()] == ["failed", "delivered"]
    assert retry_after_delivered_res.status_code == 409


def test_lifecycle_webhook_events_are_queued(auth_client, partner_a_headers):
    create_res = create_incident(
        auth_client,
        site_id="SITE-WEBHOOK-002",
        headers=partner_a_headers,
        source_event_id="SRC-WEBHOOK-002",
    )
    incident_id = create_res.json()["incident"]["id"]

    duplicate_res = auth_client.post(
        "/api/v1/incidents",
        headers=partner_a_headers,
        json={
            "client_name": "DemoEnterprisePartner",
            "site_id": "SITE-WEBHOOK-002",
            "province": "North Zone",
            "scada_status": "OUTAGE_CONFIRMED",
            "source_event_id": "SRC-WEBHOOK-002",
        },
    )
    signal_res = auth_client.post(
        f"/api/v1/incidents/{incident_id}/signals/field",
        headers=partner_a_headers,
        json={"channel": "FIELD_APP", "raw_text": "Pole down near segment A"},
    )
    restore_res = auth_client.post(
        f"/api/v1/incidents/{incident_id}/restore",
        headers=partner_a_headers,
        json={"restored_by": "SCADA_SENSOR"},
    )
    deliveries = auth_client.get("/api/v1/webhook-deliveries", headers=partner_a_headers).json()
    event_types = [delivery["event_type"] for delivery in deliveries]

    assert duplicate_res.status_code == 200
    assert signal_res.status_code == 200
    assert restore_res.status_code == 200
    assert "incident.created" in event_types
    assert "duplicate.ignored" in event_types
    assert "eta.revised" in event_types
    assert "incident.restored" in event_types


def test_timeout_webhook_event_is_queued(auth_client, partner_a_headers):
    create_res = create_incident(auth_client, site_id="SITE-WEBHOOK-003", headers=partner_a_headers)
    incident_id = create_res.json()["incident"]["id"]
    auth_client.app.state.service.force_backdate_incident(incident_id, minutes_ago=121)

    timeout_res = auth_client.post(f"/api/v1/incidents/{incident_id}/timeout-check", headers=partner_a_headers)
    deliveries = auth_client.get("/api/v1/webhook-deliveries", headers=partner_a_headers).json()

    assert timeout_res.status_code == 200
    assert "timeout.applied" in [delivery["event_type"] for delivery in deliveries]


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

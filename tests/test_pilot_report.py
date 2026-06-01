from __future__ import annotations

import json

from scripts.generate_pilot_report import build_pilot_report, render_markdown


SENSITIVE_REPORT_TERMS = [
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


def test_private_pilot_report_shape_is_public_safe(client):
    rows = [
        {
            "incident_id": "SYN-PILOT-1",
            "actual_restoration_duration_hours": 2.0,
            "initial_eta_hours": 2.5,
            "eta_error_hours": 0.5,
            "audit_event_count": 2,
            "feature_snapshot": {"timeout_applied": False},
        },
        {
            "incident_id": "SYN-PILOT-2",
            "actual_restoration_duration_hours": 6.0,
            "initial_eta_hours": 3.0,
            "eta_error_hours": -3.0,
            "audit_event_count": 3,
            "feature_snapshot": {"timeout_applied": True},
        },
    ]

    report = build_pilot_report(
        service=client.app.state.service,
        closed_rows=rows,
        input_label="synthetic-test-rows",
    )
    report_text = json.dumps(report)

    assert report["report_type"] == "private-pilot-evidence-pack"
    assert report["data_boundary"] == "synthetic-public-safe"
    assert report["readiness"]["pilot_discussion_ready"] is True
    assert report["readiness"]["production_ready"] is False
    assert report["pilot_success_metrics"]["eta_mae_hours"] == 1.75
    assert "webhook_delivery_rate" in report["pilot_success_metrics"]
    assert "partner_action_distribution" in report["pilot_success_metrics"]
    assert "sandbox_integration_evidence" in report
    assert report["sandbox_integration_evidence"]["mode"] == "local-outbox-only"
    assert report["sandbox_integration_evidence"]["outbound_http_sent"] is False
    assert "readiness_gate" in report
    assert report["readiness_gate"]["readiness"]["sandbox_pilot_ready"] is True
    assert report["readiness_gate"]["readiness"]["production_ready"] is False
    assert report["production_gaps"]
    for term in SENSITIVE_REPORT_TERMS:
        assert term not in report_text


def test_private_pilot_markdown_report_is_actionable_and_public_safe(client):
    rows = [
        {
            "incident_id": "SYN-PILOT-3",
            "actual_restoration_duration_hours": 1.5,
            "initial_eta_hours": 2.0,
            "eta_error_hours": 0.5,
            "audit_event_count": 1,
            "feature_snapshot": {"timeout_applied": False},
        }
    ]

    report = build_pilot_report(
        service=client.app.state.service,
        closed_rows=rows,
        input_label="synthetic-test-rows",
    )
    markdown = render_markdown(report)

    assert "# Private Pilot Evidence Report" in markdown
    assert "Sandbox Integration Evidence" in markdown
    assert "Readiness Gate" in markdown
    assert "Pilot Success Metrics" in markdown
    assert "Production Gaps" in markdown
    for term in SENSITIVE_REPORT_TERMS:
        assert term not in markdown

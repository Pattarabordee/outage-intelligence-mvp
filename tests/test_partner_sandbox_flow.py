from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from apps.api.services import IncidentService
from scripts.generate_pilot_report import build_pilot_report, render_markdown
from scripts.run_partner_sandbox_flow import SENSITIVE_OUTPUT_TERMS, run_partner_sandbox_flow

ROOT = Path(__file__).resolve().parents[1]


def test_partner_sandbox_flow_output_shape_and_retry_proof(tmp_path):
    service = IncidentService(db_path=tmp_path / "sandbox-flow.db")

    summary = run_partner_sandbox_flow(service)
    summary_text = json.dumps(summary, default=str)

    assert summary["scenario"]["name"] == "partner-sandbox-integration-readiness"
    assert summary["scenario"]["data_boundary"] == "synthetic-public-safe"
    assert summary["scenario"]["outbound_http_sent"] is False
    assert summary["incident_id"].startswith("INC-")
    assert summary["idempotency_result"]["first_created"] is True
    assert summary["idempotency_result"]["duplicate_created"] is False
    assert summary["idempotency_result"]["same_incident_id"] is True
    assert summary["idempotency_result"]["duplicate_signal_ignored"] is True
    assert summary["webhook_retry_result"]["final_status"] == "delivered"
    assert summary["webhook_retry_result"]["attempt_outcomes"] == ["failed", "delivered"]
    assert summary["webhook_retry_result"]["outbound_http_sent"] is False
    assert summary["restore_result"]["first_status"] == "CLOSED"
    assert summary["restore_result"]["second_status"] == "CLOSED"
    assert summary["restore_result"]["idempotent"] is True
    assert summary["restore_result"]["closed_event_count"] == 1
    assert summary["timeout_result"]["timeout_applied"] is True
    assert summary["timeout_result"]["reason_code"] == "TIMEOUT_FAILSAFE"
    assert summary["report_ready"] is True
    assert summary["public_safe_checks"]["status"] == "passed"
    for term in SENSITIVE_OUTPUT_TERMS:
        assert term not in summary_text


def test_partner_sandbox_cli_outputs_public_safe_json():
    result = subprocess.run(
        [sys.executable, "scripts/run_partner_sandbox_flow.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    output_text = result.stdout

    assert payload["report_ready"] is True
    assert payload["public_safe_checks"]["status"] == "passed"
    assert payload["sandbox_integration_evidence"]["flow_status"]["incident_create_covered"] is True
    assert payload["sandbox_integration_evidence"]["flow_status"]["eta_revision_covered"] is True
    assert payload["sandbox_integration_evidence"]["flow_status"]["timeout_failsafe_covered"] is True
    assert payload["sandbox_integration_evidence"]["flow_status"]["restoration_closed_loop_covered"] is True
    for term in SENSITIVE_OUTPUT_TERMS:
        assert term not in output_text


def test_pilot_report_includes_sandbox_integration_evidence(tmp_path):
    service = IncidentService(db_path=tmp_path / "pilot-report-flow.db")
    run_partner_sandbox_flow(service)

    report = build_pilot_report(
        service=service,
        closed_rows=service.export_closed_incidents_dataset(),
        input_label="sandbox-flow-runtime",
    )
    markdown = render_markdown(report)
    report_text = json.dumps(report, default=str) + markdown

    evidence = report["sandbox_integration_evidence"]
    assert evidence["mode"] == "local-outbox-only"
    assert evidence["outbound_http_sent"] is False
    assert evidence["flow_coverage_rate"] == 1.0
    assert evidence["retry_behavior"]["attempt_records"] >= 2
    assert evidence["report_readiness"]["can_generate_pilot_report"] is True
    assert "Sandbox Integration Evidence" in markdown
    for term in SENSITIVE_OUTPUT_TERMS:
        assert term not in report_text


def test_partner_sandbox_playbook_is_public_safe():
    playbook = (ROOT / "docs" / "partner-sandbox-playbook.md").read_text(encoding="utf-8")

    assert "Partner Sandbox Integration Playbook" in playbook
    assert "run_partner_sandbox_flow.py" in playbook
    for term in SENSITIVE_OUTPUT_TERMS:
        assert term not in playbook

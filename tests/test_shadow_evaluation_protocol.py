from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.generate_pilot_report import build_pilot_report, render_markdown as render_pilot_markdown
from scripts.generate_readiness_gate import build_readiness_gate, render_markdown as render_readiness_markdown
from scripts.run_partner_sandbox_flow import SENSITIVE_OUTPUT_TERMS
from scripts.run_shadow_evaluation_protocol import (
    build_shadow_evaluation_protocol,
    load_contract,
    load_rows,
    render_markdown,
)

ROOT = Path(__file__).resolve().parents[1]


def _assert_public_safe_output(text: str) -> None:
    for term in SENSITIVE_OUTPUT_TERMS:
        assert term not in text


def test_shadow_evaluation_protocol_shape_and_public_safe_output():
    report = build_shadow_evaluation_protocol(rows=load_rows(), contract=load_contract())
    markdown = render_markdown(report)
    rendered = json.dumps(report, default=str) + markdown

    assert report["report_type"] == "pilot-shadow-evaluation-protocol"
    assert report["data_boundary"] == "synthetic-public-safe"
    assert report["protocol_version"] == "shadow-eval-v1"
    assert report["contract_version"] == "pilot-data-contract-v1"
    assert report["shadow_evaluation_ready"] is True
    assert report["contract_validation"]["rows"] == 24
    assert report["contract_validation"]["required_field_coverage"] == 1.0
    assert report["contract_validation"]["feature_snapshot_coverage"] == 1.0
    assert report["contract_validation"]["partner_class_count"] == 5
    assert report["contract_validation"]["scada_status_count"] == 3
    assert report["contract_validation"]["prolonged_case_count"] >= 4
    assert report["benchmark_summary"]["best_policy_by_mae"] == "scada_status_group_mean"
    assert report["public_safe_checks"]["status"] == "passed"
    assert all(check["status"] == "passed" for check in report["acceptance_checks"])
    assert "Pilot Shadow Evaluation Protocol" in markdown
    _assert_public_safe_output(rendered)


def test_shadow_evaluation_protocol_flags_contract_gaps_without_crashing():
    rows = [
        {
            "incident_id": "SYN-BAD-1",
            "prediction_time": "2026-03-01T00:00:00+00:00",
            "actual_restoration_duration_hours": 1.0,
            "initial_eta_hours": 2.0,
            "eta_error_hours": 1.0,
            "rule_version": "rules-v1",
            "audit_event_count": 1,
            "feature_snapshot": {
                "partner_id": "partner-shadow-bad",
                "partner_class": "telecom",
                "scada_status": "OUTAGE_CONFIRMED",
                "province": "North Zone",
                "source_event_id_present": True,
            },
        }
    ]

    report = build_shadow_evaluation_protocol(rows=rows, contract=load_contract(), input_label="synthetic-bad-row")

    assert report["shadow_evaluation_ready"] is False
    assert report["contract_validation"]["rows"] == 1
    assert "timeout_applied" in report["contract_validation"]["missing_feature_snapshot_fields"]
    assert any(check["name"] == "minimum_rows" and check["status"] == "needs_review" for check in report["acceptance_checks"])
    assert report["public_safe_checks"]["status"] == "passed"


def test_shadow_evaluation_protocol_cli_outputs_public_safe_json_and_markdown():
    json_result = subprocess.run(
        [sys.executable, "scripts/run_shadow_evaluation_protocol.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(json_result.stdout)

    markdown_result = subprocess.run(
        [sys.executable, "scripts/run_shadow_evaluation_protocol.py", "--format", "markdown"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert payload["shadow_evaluation_ready"] is True
    assert payload["contract_validation"]["rows"] == 24
    assert payload["public_safe_checks"]["status"] == "passed"
    assert "# Pilot Shadow Evaluation Protocol" in markdown_result.stdout
    _assert_public_safe_output(json_result.stdout + markdown_result.stdout)


def test_readiness_gate_includes_shadow_evaluation_evidence():
    report = build_readiness_gate(root=ROOT)
    markdown = render_readiness_markdown(report)
    rendered = json.dumps(report, default=str) + markdown

    assert "shadow_evaluation" in report
    assert report["shadow_evaluation"]["shadow_evaluation_ready"] is True
    assert report["shadow_evaluation"]["rows"] == 24
    assert report["shadow_evaluation"]["required_field_coverage"] == 1.0
    assert report["shadow_evaluation"]["feature_snapshot_coverage"] == 1.0
    assert report["shadow_evaluation"]["production_ready"] is False
    assert any(
        check["name"] == "shadow_evaluation_protocol" and check["status"] == "passed"
        for check in report["checks"]
    )
    assert "Shadow Evaluation Protocol" in markdown
    _assert_public_safe_output(rendered)


def test_pilot_report_includes_shadow_evaluation_evidence(client):
    report = build_pilot_report(service=client.app.state.service, closed_rows=[], input_label="empty-test-rows")
    markdown = render_pilot_markdown(report)
    rendered = json.dumps(report, default=str) + markdown

    assert "shadow_evaluation_evidence" in report
    assert report["shadow_evaluation_evidence"]["shadow_evaluation_ready"] is True
    assert report["shadow_evaluation_evidence"]["contract_validation"]["rows"] == 24
    assert report["shadow_evaluation_evidence"]["public_safe_checks"]["status"] == "passed"
    assert "Shadow Evaluation Evidence" in markdown
    _assert_public_safe_output(rendered)


def test_shadow_evaluation_docs_and_contract_are_public_safe():
    files = [
        ROOT / "docs" / "pilot-data-contract.md",
        ROOT / "docs" / "shadow-evaluation-protocol.md",
        ROOT / "data" / "synthetic" / "pilot_data_contract.json",
        ROOT / "data" / "synthetic" / "shadow_eval_closed_incidents.jsonl",
    ]

    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)

    assert "Pilot Data Contract" in combined
    assert "Shadow Evaluation Protocol" in combined
    assert "pilot-data-contract-v1" in combined
    _assert_public_safe_output(combined)

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.generate_pilot_report import build_pilot_report, render_markdown as render_pilot_markdown
from scripts.generate_readiness_gate import build_readiness_gate
from scripts.run_partner_sandbox_flow import SENSITIVE_OUTPUT_TERMS
from scripts.run_pilot_scenario_matrix import (
    load_scenario_catalog,
    render_markdown,
    run_pilot_scenario_matrix,
)

ROOT = Path(__file__).resolve().parents[1]


def _assert_public_safe_output(text: str) -> None:
    for term in SENSITIVE_OUTPUT_TERMS:
        assert term not in text


def test_pilot_scenario_catalog_covers_private_pilot_questions():
    catalog = load_scenario_catalog()
    scenario_ids = {scenario["id"] for scenario in catalog["scenarios"]}
    capabilities = {capability for scenario in catalog["scenarios"] for capability in scenario["capabilities"]}

    assert catalog["data_boundary"] == "synthetic-public-safe"
    assert {
        "short-outage-restored",
        "prolonged-outage-eta-revised",
        "timeout-failsafe-applied",
        "duplicate-event-and-signal",
        "webhook-retry-exhausted",
        "restore-endpoint-idempotent",
        "partner-scope-denied",
    }.issubset(scenario_ids)
    assert {
        "short_outage",
        "prolonged_outage",
        "timeout_failsafe",
        "duplicate_event",
        "duplicate_signal",
        "retry_exhausted",
        "restore_idempotency",
        "partner_scope",
    }.issubset(capabilities)


def test_pilot_scenario_matrix_shape_and_public_safe_output():
    report = run_pilot_scenario_matrix()
    markdown = render_markdown(report)
    rendered = json.dumps(report, default=str) + markdown

    assert report["report_type"] == "pilot-scenario-matrix"
    assert report["scenario_count"] == 7
    assert report["passed"] == 7
    assert report["failed"] == 0
    assert report["public_safe_checks"]["status"] == "passed"
    assert all(result["status"] == "passed" for result in report["scenario_results"])
    assert report["coverage_by_capability"]["timeout_failsafe"]["passed"] == 1
    assert report["coverage_by_capability"]["retry_exhausted"]["passed"] == 1
    assert report["coverage_by_capability"]["partner_scope"]["passed"] == 1
    assert "Pilot Scenario Matrix" in markdown
    _assert_public_safe_output(rendered)


def test_pilot_scenario_matrix_cli_outputs_public_safe_json():
    result = subprocess.run(
        [sys.executable, "scripts/run_pilot_scenario_matrix.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["passed"] == payload["scenario_count"]
    assert payload["failed"] == 0
    assert payload["public_safe_checks"]["status"] == "passed"
    _assert_public_safe_output(result.stdout)


def test_readiness_gate_includes_scenario_matrix_evidence():
    report = build_readiness_gate(root=ROOT)

    assert "scenario_matrix" in report
    assert report["scenario_matrix"]["scenario_count"] == 7
    assert report["scenario_matrix"]["failed"] == 0
    assert report["scenario_matrix"]["public_safe_status"] == "passed"
    assert any(check["name"] == "scenario_matrix" and check["status"] == "passed" for check in report["checks"])


def test_pilot_report_includes_scenario_matrix_evidence(client):
    report = build_pilot_report(service=client.app.state.service, closed_rows=[], input_label="empty-test-rows")
    markdown = render_pilot_markdown(report)
    rendered = json.dumps(report, default=str) + markdown

    assert "scenario_matrix_evidence" in report
    assert report["scenario_matrix_evidence"]["scenario_count"] == 7
    assert report["scenario_matrix_evidence"]["failed"] == 0
    assert "Scenario Matrix Evidence" in markdown
    _assert_public_safe_output(rendered)


def test_pilot_scenario_matrix_doc_is_public_safe():
    text = (ROOT / "docs" / "pilot-scenario-matrix.md").read_text(encoding="utf-8")

    assert "Pilot Scenario Matrix" in text
    assert "run_pilot_scenario_matrix.py" in text
    assert "production_ready" in text
    _assert_public_safe_output(text)

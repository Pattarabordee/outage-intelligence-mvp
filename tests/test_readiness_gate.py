from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.generate_readiness_gate import build_readiness_gate, render_markdown
from scripts.public_safe_scan import scan_public_safe
from scripts.run_partner_sandbox_flow import SENSITIVE_OUTPUT_TERMS

ROOT = Path(__file__).resolve().parents[1]


def _assert_public_safe_output(text: str) -> None:
    for term in SENSITIVE_OUTPUT_TERMS:
        assert term not in text


def test_public_safe_scan_passes_with_allowlisted_contract_references():
    report = scan_public_safe(root=ROOT)
    report_text = json.dumps(report, default=str)

    assert report["report_type"] == "public-safe-scan"
    assert report["status"] == "passed"
    assert report["issues"] == []
    assert report["scanned_files"] > 0
    _assert_public_safe_output(report_text)


def test_readiness_gate_shape_and_markdown_are_public_safe():
    report = build_readiness_gate(root=ROOT)
    markdown = render_markdown(report)
    rendered = json.dumps(report, default=str) + markdown

    assert report["report_type"] == "private-sandbox-readiness-gate"
    assert report["data_boundary"] == "synthetic-public-safe"
    assert report["readiness"]["prototype_ready"] is True
    assert report["readiness"]["sandbox_pilot_ready"] is True
    assert report["readiness"]["production_ready"] is False
    assert report["readiness"]["gate_decision"] == "ready_for_private_sandbox_discussion"
    assert len(report["passed_checks"]) == len(report["checks"])
    assert report["public_safe_scan"]["status"] == "passed"
    assert report["scenario_matrix"]["scenario_count"] == 7
    assert report["scenario_matrix"]["failed"] == 0
    assert report["sandbox_integration"]["outbound_http_sent"] is False
    assert report["sandbox_integration"]["flow_coverage_rate"] == 1.0
    assert "Private Sandbox Readiness Gate" in markdown
    _assert_public_safe_output(rendered)


def test_public_safe_scan_cli_outputs_public_safe_json():
    result = subprocess.run(
        [sys.executable, "scripts/public_safe_scan.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["status"] == "passed"
    assert payload["issues"] == []
    _assert_public_safe_output(result.stdout)


def test_readiness_gate_cli_outputs_public_safe_json():
    result = subprocess.run(
        [sys.executable, "scripts/generate_readiness_gate.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["readiness"]["sandbox_pilot_ready"] is True
    assert payload["readiness"]["production_ready"] is False
    assert payload["public_safe_scan"]["status"] == "passed"
    assert payload["scenario_matrix"]["failed"] == 0
    assert payload["sandbox_integration"]["flow_coverage_rate"] == 1.0
    _assert_public_safe_output(result.stdout)


def test_private_sandbox_acceptance_criteria_doc_is_public_safe():
    text = (ROOT / "docs" / "private-sandbox-acceptance-criteria.md").read_text(encoding="utf-8")

    assert "Private Sandbox Acceptance Criteria" in text
    assert "generate_readiness_gate.py" in text
    assert "ready_for_private_sandbox_discussion" in text
    _assert_public_safe_output(text)

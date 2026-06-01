from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.generate_partner_pilot_pack import (
    build_partner_pilot_pack,
    load_onboarding_checklist,
    render_markdown,
)
from scripts.run_partner_sandbox_flow import SENSITIVE_OUTPUT_TERMS

ROOT = Path(__file__).resolve().parents[1]
EXTRA_PRIVATE_TERMS = ["credential", "token"]


def _assert_public_safe_output(text: str) -> None:
    for term in SENSITIVE_OUTPUT_TERMS + EXTRA_PRIVATE_TERMS:
        assert term not in text


def test_partner_pilot_pack_shape_and_markdown_are_public_safe():
    report = build_partner_pilot_pack(root=ROOT)
    markdown = render_markdown(report)
    rendered = json.dumps(report, default=str) + markdown

    assert report["report_type"] == "partner-pilot-onboarding-pack"
    assert report["data_boundary"] == "synthetic-public-safe"
    assert report["pack_version"] == "partner-pilot-pack-v1"
    assert report["pack_ready"] is True
    assert report["readiness_decision"]["sandbox_pilot_ready"] is True
    assert report["readiness_decision"]["production_ready"] is False
    assert report["governance"]["no_live_partner_dispatch"] is True
    assert report["governance"]["no_outbound_network_delivery"] is True
    assert report["governance"]["no_model_deployed"] is True
    assert report["onboarding"]["required_items_accounted_for"] is True
    assert report["onboarding"]["status_counts"]["ready_for_discussion"] >= 1
    assert report["onboarding"]["needs_private_pilot_input"]
    assert report["onboarding"]["production_gaps"]
    assert report["readiness_evidence"]["public_safe_scan_status"] == "passed"
    assert report["readiness_evidence"]["scenario_matrix_failed"] == 0
    assert report["shadow_evaluation"]["production_ready"] is False
    assert report["public_safe_checks"]["status"] == "passed"
    assert all(check["status"] == "passed" for check in report["acceptance_checks"])
    assert "# Partner Pilot Onboarding Pack" in markdown
    assert "Governance Boundary" in markdown
    assert "Risk Register" in markdown
    _assert_public_safe_output(rendered)


def test_partner_pilot_pack_cli_outputs_public_safe_json_and_markdown():
    json_result = subprocess.run(
        [sys.executable, "scripts/generate_partner_pilot_pack.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(json_result.stdout)

    markdown_result = subprocess.run(
        [sys.executable, "scripts/generate_partner_pilot_pack.py", "--format", "markdown"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert payload["pack_ready"] is True
    assert payload["readiness_decision"]["production_ready"] is False
    assert payload["public_safe_checks"]["status"] == "passed"
    assert "# Partner Pilot Onboarding Pack" in markdown_result.stdout
    _assert_public_safe_output(json_result.stdout + markdown_result.stdout)


def test_partner_pilot_onboarding_docs_and_checklist_are_public_safe():
    files = [
        ROOT / "data" / "synthetic" / "partner_pilot_onboarding_checklist.json",
        ROOT / "docs" / "partner-pilot-onboarding.md",
        ROOT / "docs" / "private-pilot-governance.md",
        ROOT / "docs" / "pilot-risk-register.md",
    ]

    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    checklist = load_onboarding_checklist()

    assert checklist["version"] == "partner-pilot-onboarding-v1"
    assert checklist["data_boundary"] == "synthetic-public-safe"
    assert "Partner Pilot Onboarding" in combined
    assert "Private Pilot Governance" in combined
    assert "Pilot Risk Register" in combined
    _assert_public_safe_output(combined)

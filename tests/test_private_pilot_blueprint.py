from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.generate_private_pilot_blueprint import (
    build_private_pilot_blueprint_report,
    load_blueprint,
    render_markdown,
)
from scripts.run_partner_sandbox_flow import SENSITIVE_OUTPUT_TERMS

ROOT = Path(__file__).resolve().parents[1]
EXTRA_PRIVATE_TERMS = ["credential", "token"]


def _assert_public_safe_output(text: str) -> None:
    for term in SENSITIVE_OUTPUT_TERMS + EXTRA_PRIVATE_TERMS:
        assert term not in text


def test_private_pilot_blueprint_shape_and_markdown_are_public_safe():
    report = build_private_pilot_blueprint_report(root=ROOT)
    markdown = render_markdown(report)
    rendered = json.dumps(report, default=str) + markdown

    assert report["report_type"] == "private-pilot-implementation-blueprint"
    assert report["data_boundary"] == "synthetic-public-safe"
    assert report["blueprint_version"] == "private-pilot-blueprint-v1"
    assert report["blueprint_ready"] is True
    assert report["implementation_decision"]["prototype_ready"] is True
    assert report["implementation_decision"]["sandbox_pilot_ready"] is True
    assert report["implementation_decision"]["private_pilot_ready"] is False
    assert report["implementation_decision"]["production_ready"] is False
    assert report["maturity"]["private_pilot_status"] == "requires_private_build"
    assert report["maturity"]["production_status"] == "not_ready"
    assert report["workstream_summary"]["workstream_count"] >= 8
    assert report["workstream_summary"]["all_workstreams_have_private_requirement"] is True
    assert report["workstream_summary"]["all_workstreams_have_production_gate"] is True
    assert report["partner_pack_evidence"]["pack_ready"] is True
    assert report["partner_pack_evidence"]["public_safe_status"] == "passed"
    assert report["public_safe_checks"]["status"] == "passed"
    assert all(check["status"] == "passed" for check in report["acceptance_checks"])
    assert "# Private Pilot Implementation Blueprint" in markdown
    assert "Implementation Decision" in markdown
    assert "Security Model" in markdown
    assert "Deployment And Release Gates" in markdown
    _assert_public_safe_output(rendered)


def test_private_pilot_blueprint_cli_outputs_public_safe_json_and_markdown():
    json_result = subprocess.run(
        [sys.executable, "scripts/generate_private_pilot_blueprint.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(json_result.stdout)

    markdown_result = subprocess.run(
        [sys.executable, "scripts/generate_private_pilot_blueprint.py", "--format", "markdown"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert payload["blueprint_ready"] is True
    assert payload["implementation_decision"]["private_pilot_ready"] is False
    assert payload["implementation_decision"]["production_ready"] is False
    assert payload["public_safe_checks"]["status"] == "passed"
    assert "# Private Pilot Implementation Blueprint" in markdown_result.stdout
    _assert_public_safe_output(json_result.stdout + markdown_result.stdout)


def test_private_pilot_blueprint_docs_and_data_are_public_safe():
    files = [
        ROOT / "data" / "synthetic" / "private_pilot_implementation_blueprint.json",
        ROOT / "docs" / "private-pilot-implementation-blueprint.md",
        ROOT / "docs" / "private-pilot-transition-gates.md",
        ROOT / "scripts" / "generate_private_pilot_blueprint.py",
    ]

    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    blueprint = load_blueprint()

    assert blueprint["version"] == "private-pilot-blueprint-v1"
    assert blueprint["data_boundary"] == "synthetic-public-safe"
    assert len(blueprint["workstreams"]) >= 8
    assert "Private Pilot Implementation Blueprint" in combined
    assert "Private Pilot Transition Gates" in combined
    _assert_public_safe_output(combined)

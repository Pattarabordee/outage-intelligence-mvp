from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.generate_pilot_report import build_pilot_report, render_markdown as render_pilot_markdown
from scripts.generate_readiness_gate import build_readiness_gate
from scripts.run_ml_baseline_benchmark import (
    build_ml_baseline_benchmark,
    load_rows,
    render_markdown,
)
from scripts.run_partner_sandbox_flow import SENSITIVE_OUTPUT_TERMS

ROOT = Path(__file__).resolve().parents[1]


def _assert_public_safe_output(text: str) -> None:
    for term in SENSITIVE_OUTPUT_TERMS:
        assert term not in text


def test_ml_baseline_benchmark_shape_and_public_safe_output():
    report = build_ml_baseline_benchmark(rows=load_rows(), input_label="data/synthetic/closed_incidents.jsonl")
    markdown = render_markdown(report)
    rendered = json.dumps(report, default=str) + markdown

    assert report["report_type"] == "ml-baseline-benchmark"
    assert report["data_boundary"] == "synthetic-public-safe"
    assert report["benchmark_ready"] is True
    assert report["dataset"]["rows"] == 8
    assert report["dataset"]["train_rows"] == 6
    assert report["dataset"]["test_rows"] == 2
    assert set(report["policies"]) == {
        "rules_initial_eta",
        "global_mean_duration",
        "scada_status_group_mean",
        "partner_class_group_mean",
    }
    assert report["benchmark_summary"]["primary_metric"] == "mae_hours"
    assert report["benchmark_summary"]["best_policy_by_mae"] == "scada_status_group_mean"
    assert report["governance"]["no_model_deployed"] is True
    assert report["governance"]["production_ready"] is False
    assert report["public_safe_checks"]["status"] == "passed"
    assert "ML Baseline Benchmark" in markdown
    _assert_public_safe_output(rendered)


def test_ml_baseline_benchmark_reports_insufficient_rows_without_crashing():
    report = build_ml_baseline_benchmark(
        rows=[
            {
                "incident_id": "SYN-TINY-1",
                "actual_restoration_duration_hours": 1.0,
                "initial_eta_hours": 2.0,
                "feature_snapshot": {"scada_status": "OUTAGE_CONFIRMED", "partner_class": "telecom"},
            }
        ],
        input_label="synthetic-test-rows",
    )
    markdown = render_markdown(report)

    assert report["benchmark_ready"] is False
    assert report["dataset"]["minimum_rows"] == 4
    assert report["policies"] == {}
    assert report["public_safe_checks"]["status"] == "passed"
    assert "Insufficient synthetic closed incidents" in report["benchmark_summary"]["interpretation"]
    _assert_public_safe_output(json.dumps(report, default=str) + markdown)


def test_ml_baseline_benchmark_cli_outputs_public_safe_json_and_markdown():
    json_result = subprocess.run(
        [sys.executable, "scripts/run_ml_baseline_benchmark.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(json_result.stdout)

    markdown_result = subprocess.run(
        [sys.executable, "scripts/run_ml_baseline_benchmark.py", "--format", "markdown"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert payload["benchmark_ready"] is True
    assert payload["public_safe_checks"]["status"] == "passed"
    assert "# ML Baseline Benchmark" in markdown_result.stdout
    _assert_public_safe_output(json_result.stdout + markdown_result.stdout)


def test_readiness_gate_includes_ml_baseline_evidence():
    report = build_readiness_gate(root=ROOT)

    assert "ml_baseline" in report
    assert report["ml_baseline"]["benchmark_ready"] is True
    assert report["ml_baseline"]["policy_count"] == 4
    assert report["ml_baseline"]["public_safe_status"] == "passed"
    assert report["ml_baseline"]["no_model_deployed"] is True
    assert report["ml_baseline"]["production_ready"] is False
    assert any(check["name"] == "ml_baseline_benchmark" and check["status"] == "passed" for check in report["checks"])


def test_pilot_report_includes_ml_baseline_evidence(client):
    report = build_pilot_report(
        service=client.app.state.service,
        closed_rows=load_rows(),
        input_label="data/synthetic/closed_incidents.jsonl",
    )
    markdown = render_pilot_markdown(report)
    rendered = json.dumps(report, default=str) + markdown

    assert "ml_baseline_evidence" in report
    assert report["ml_baseline_evidence"]["benchmark_ready"] is True
    assert report["ml_baseline_evidence"]["public_safe_checks"]["status"] == "passed"
    assert report["ml_baseline_evidence"]["governance"]["no_model_deployed"] is True
    assert "ML Baseline Evidence" in markdown
    _assert_public_safe_output(rendered)


def test_ml_baseline_benchmark_doc_is_public_safe():
    text = (ROOT / "docs" / "ml-baseline-benchmark.md").read_text(encoding="utf-8")

    assert "ML Baseline Benchmark" in text
    assert "run_ml_baseline_benchmark.py" in text
    assert "production_ready" not in text
    _assert_public_safe_output(text)

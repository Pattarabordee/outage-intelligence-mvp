from __future__ import annotations

from scripts.evaluate_product_metrics import evaluate_rows


def test_product_metrics_report_shape():
    rows = [
        {
            "incident_id": "SYN-1",
            "actual_restoration_duration_hours": 2.0,
            "initial_eta_hours": 2.5,
            "eta_error_hours": 0.5,
            "audit_event_count": 2,
            "feature_snapshot": {"timeout_applied": False},
        },
        {
            "incident_id": "SYN-2",
            "actual_restoration_duration_hours": 6.0,
            "initial_eta_hours": 3.0,
            "eta_error_hours": -3.0,
            "audit_event_count": 3,
            "feature_snapshot": {"timeout_applied": True},
        },
    ]

    report = evaluate_rows(rows, prolonged_threshold_hours=4.0)

    assert report["rows"] == 2
    assert report["eta_mae_hours"] == 1.75
    assert report["underestimation_rate"] == 0.5
    assert report["timeout_fallback_rate"] == 0.5
    assert report["audit_completeness_rate"] == 1.0
    assert report["restoration_ground_truth_coverage"] == 1.0
    assert report["prolonged_outage_baseline"]["recall"] == 0.0

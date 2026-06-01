from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_DATASET = ROOT / "data" / "synthetic" / "closed_incidents.jsonl"


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def rate(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def evaluate_rows(rows: list[dict], prolonged_threshold_hours: float = 4.0) -> dict:
    if not rows:
        raise ValueError("Evaluation requires at least one closed incident row.")

    eta_errors = [abs(row["eta_error_hours"]) for row in rows]
    underestimates = [row for row in rows if row["eta_error_hours"] < 0]
    timeouts = [row for row in rows if row.get("feature_snapshot", {}).get("timeout_applied", False)]
    complete_audits = [row for row in rows if row.get("audit_event_count", 1) >= 1]
    ground_truth = [row for row in rows if row.get("actual_restoration_duration_hours") is not None]
    prolonged_actual = [
        row for row in rows if row["actual_restoration_duration_hours"] >= prolonged_threshold_hours
    ]
    prolonged_predicted = [row for row in rows if row["initial_eta_hours"] >= prolonged_threshold_hours]
    true_positive = {
        row["incident_id"]
        for row in prolonged_actual
        if row["initial_eta_hours"] >= prolonged_threshold_hours
    }

    return {
        "rows": len(rows),
        "eta_mae_hours": round(statistics.fmean(eta_errors), 3),
        "underestimation_rate": rate(len(underestimates), len(rows)),
        "timeout_fallback_rate": rate(len(timeouts), len(rows)),
        "audit_completeness_rate": rate(len(complete_audits), len(rows)),
        "restoration_ground_truth_coverage": rate(len(ground_truth), len(rows)),
        "prolonged_outage_baseline": {
            "threshold_hours": prolonged_threshold_hours,
            "predicted_positive_rate": rate(len(prolonged_predicted), len(rows)),
            "recall": rate(len(true_positive), len(prolonged_actual)),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate product metrics from closed incident JSONL.")
    parser.add_argument("--input", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--prolonged-threshold-hours", type=float, default=4.0)
    args = parser.parse_args()

    report = evaluate_rows(load_rows(args.input), prolonged_threshold_hours=args.prolonged_threshold_hours)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_DATASET = ROOT / "data" / "synthetic" / "closed_incidents.jsonl"


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def train_group_mean(rows: list[dict]) -> tuple[dict[str, float], float]:
    durations_by_status: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        status = row["feature_snapshot"]["scada_status"]
        durations_by_status[status].append(row["actual_restoration_duration_hours"])

    global_mean = statistics.fmean(row["actual_restoration_duration_hours"] for row in rows)
    model = {status: statistics.fmean(values) for status, values in durations_by_status.items()}
    return model, global_mean


def evaluate(rows: list[dict], model: dict[str, float], fallback: float) -> dict:
    errors = []
    underestimates = 0
    for row in rows:
        status = row["feature_snapshot"]["scada_status"]
        actual = row["actual_restoration_duration_hours"]
        predicted = model.get(status, fallback)
        error = predicted - actual
        errors.append(abs(error))
        if error < 0:
            underestimates += 1

    return {
        "rows": len(rows),
        "mae_hours": round(statistics.fmean(errors), 3),
        "underestimation_rate": round(underestimates / len(rows), 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a simple ETA baseline from closed incident JSONL.")
    parser.add_argument("--input", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--test-size", type=float, default=0.25)
    args = parser.parse_args()

    rows = load_rows(args.input)
    if len(rows) < 4:
        raise SystemExit("Need at least 4 closed incident rows for a meaningful baseline split.")

    split_index = max(1, int(len(rows) * (1 - args.test_size)))
    train_rows = rows[:split_index]
    test_rows = rows[split_index:]
    model, fallback = train_group_mean(train_rows)
    report = {
        "model": "group_mean_by_scada_status",
        "train_rows": len(train_rows),
        "test": evaluate(test_rows, model, fallback),
        "groups": {key: round(value, 3) for key, value in model.items()},
        "fallback_hours": round(fallback, 3),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.reporting import evaluate_rows

DEFAULT_DATASET = ROOT / "data" / "synthetic" / "closed_incidents.jsonl"


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate product metrics from closed incident JSONL.")
    parser.add_argument("--input", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--prolonged-threshold-hours", type=float, default=4.0)
    args = parser.parse_args()

    report = evaluate_rows(load_rows(args.input), prolonged_threshold_hours=args.prolonged_threshold_hours)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

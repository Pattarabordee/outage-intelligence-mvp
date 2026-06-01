from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.services import IncidentService


def main() -> None:
    parser = argparse.ArgumentParser(description="Export closed incident records as ML-ready JSONL.")
    parser.add_argument("--output", type=Path, help="Optional JSONL output path. Prints to stdout when omitted.")
    args = parser.parse_args()

    rows = IncidentService().export_closed_incidents_dataset()
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return

    for line in lines:
        print(line)


if __name__ == "__main__":
    main()

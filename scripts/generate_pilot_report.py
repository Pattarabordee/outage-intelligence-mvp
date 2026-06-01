from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.reporting import evaluate_rows, rate
from apps.api.services import IncidentService

DEFAULT_DATASET = ROOT / "data" / "synthetic" / "closed_incidents.jsonl"


def load_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def zero_metrics() -> dict[str, Any]:
    return {
        "rows": 0,
        "eta_mae_hours": 0.0,
        "underestimation_rate": 0.0,
        "timeout_fallback_rate": 0.0,
        "audit_completeness_rate": 0.0,
        "restoration_ground_truth_coverage": 0.0,
        "prolonged_outage_baseline": {
            "threshold_hours": 4.0,
            "predicted_positive_rate": 0.0,
            "recall": 0.0,
        },
    }


def build_pilot_report(
    service: IncidentService | None = None,
    closed_rows: list[dict[str, Any]] | None = None,
    input_label: str = "data/synthetic/closed_incidents.jsonl",
) -> dict[str, Any]:
    service = service or IncidentService()
    executive_summary = service.executive_summary()
    operator_summary = service.operator_console_summary()
    deliveries = service.list_webhook_deliveries()
    rows = closed_rows if closed_rows is not None else service.export_closed_incidents_dataset()
    product_metrics = evaluate_rows(rows) if rows else zero_metrics()
    delivered_count = len([delivery for delivery in deliveries if delivery["status"] == "delivered"])
    attempted_count = len([delivery for delivery in deliveries if delivery["attempt_count"] > 0])
    action_distribution = Counter(action["recommendation"] for action in operator_summary["partner_actions"])

    return {
        "report_type": "private-pilot-evidence-pack",
        "data_boundary": "synthetic-public-safe",
        "source_dataset": input_label,
        "readiness": {
            "prototype_ready": True,
            "pilot_discussion_ready": True,
            "production_ready": False,
            "next_gate": "Private sandbox with production auth, tenant isolation, delivery worker, live telemetry, and runbooks.",
        },
        "workflow_evidence": {
            "executive_demo": {
                "route": "/demo/incidents",
                "journey_events": len(executive_summary["partner_journey"]),
                "audit_events": executive_summary["metrics"]["audit_events"],
            },
            "operator_console": {
                "route": "/demo/operator-console",
                "active_incidents": operator_summary["metrics"]["active_incidents"],
                "priority_attention_items": operator_summary["metrics"]["priority_attention_items"],
                "highest_attention_level": operator_summary["pilot_status"]["highest_attention_level"],
            },
            "webhook_outbox": {
                "records": len(deliveries),
                "delivery_rate": rate(delivered_count, len(deliveries)),
                "attempt_rate": rate(attempted_count, len(deliveries)),
                "status_counts": dict(Counter(delivery["status"] for delivery in deliveries)),
            },
        },
        "pilot_success_metrics": {
            "eta_mae_hours": product_metrics["eta_mae_hours"],
            "underestimation_rate": product_metrics["underestimation_rate"],
            "timeout_fallback_rate": product_metrics["timeout_fallback_rate"],
            "webhook_delivery_rate": rate(delivered_count, len(deliveries)),
            "webhook_attempt_rate": rate(attempted_count, len(deliveries)),
            "audit_completeness_rate": product_metrics["audit_completeness_rate"],
            "restoration_ground_truth_coverage": product_metrics["restoration_ground_truth_coverage"],
            "prolonged_outage_recall": product_metrics["prolonged_outage_baseline"]["recall"],
            "partner_action_distribution": dict(action_distribution),
        },
        "public_safe_controls": [
            "Synthetic partner, site, and incident identifiers only",
            "Private delivery headers excluded",
            "Raw field text excluded",
            "Partner network targets excluded",
            "Production topology excluded",
        ],
        "production_gaps": [
            "Production-grade authentication and partner authorization",
            "Managed database and migration plan",
            "Outbound delivery worker with receiver-side verification",
            "Live observability, alerting, and incident-owner runbooks",
            "Data retention and governance review for operational data",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    metrics = report["pilot_success_metrics"]
    evidence = report["workflow_evidence"]
    gaps = "\n".join(f"- {gap}" for gap in report["production_gaps"])
    controls = "\n".join(f"- {control}" for control in report["public_safe_controls"])
    return f"""# Private Pilot Evidence Report

Data boundary: `{report['data_boundary']}`

## Readiness

- Prototype ready: `{report['readiness']['prototype_ready']}`
- Pilot discussion ready: `{report['readiness']['pilot_discussion_ready']}`
- Production ready: `{report['readiness']['production_ready']}`
- Next gate: {report['readiness']['next_gate']}

## Workflow Evidence

- Executive route: `{evidence['executive_demo']['route']}` with {evidence['executive_demo']['journey_events']} journey events
- Operator route: `{evidence['operator_console']['route']}` with {evidence['operator_console']['priority_attention_items']} attention items
- Webhook records: `{evidence['webhook_outbox']['records']}` with delivery rate `{evidence['webhook_outbox']['delivery_rate']}`

## Pilot Success Metrics

- ETA MAE hours: `{metrics['eta_mae_hours']}`
- Underestimation rate: `{metrics['underestimation_rate']}`
- Timeout fallback rate: `{metrics['timeout_fallback_rate']}`
- Webhook delivery rate: `{metrics['webhook_delivery_rate']}`
- Webhook attempt rate: `{metrics['webhook_attempt_rate']}`
- Audit completeness rate: `{metrics['audit_completeness_rate']}`
- Restoration ground-truth coverage: `{metrics['restoration_ground_truth_coverage']}`
- Prolonged outage recall: `{metrics['prolonged_outage_recall']}`

## Public-Safe Controls

{controls}

## Production Gaps

{gaps}
"""


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a public-safe private pilot evidence report.")
    parser.add_argument("--input", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = build_pilot_report(closed_rows=load_rows(args.input), input_label=display_path(args.input))
    rendered = render_markdown(report) if args.format == "markdown" else json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + ("\n" if not rendered.endswith("\n") else ""), encoding="utf-8")
        return
    print(rendered)


if __name__ == "__main__":
    main()

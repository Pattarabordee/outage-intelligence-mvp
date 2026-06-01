from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.services import IncidentService
from scripts.public_safe_scan import scan_public_safe
from scripts.run_ml_baseline_benchmark import build_ml_baseline_benchmark
from scripts.run_partner_sandbox_flow import run_partner_sandbox_flow
from scripts.run_pilot_scenario_matrix import run_pilot_scenario_matrix


def _check(name: str, passed: bool, evidence: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "passed" if passed else "needs_review",
        "evidence": evidence,
    }


def build_readiness_gate(root: Path = ROOT) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        service = IncidentService(db_path=Path(tmpdir) / "readiness-gate.db")
        sandbox_summary = run_partner_sandbox_flow(service)

    scan = scan_public_safe(root=root)
    scenario_matrix = run_pilot_scenario_matrix()
    ml_benchmark = build_ml_baseline_benchmark()
    integration = sandbox_summary["sandbox_integration_evidence"]
    idempotency = sandbox_summary["idempotency_result"]
    retry = sandbox_summary["webhook_retry_result"]
    restore = sandbox_summary["restore_result"]
    timeout = sandbox_summary["timeout_result"]

    checks = [
        _check(
            "public_safe_scan",
            scan["status"] == "passed",
            f"{scan['scanned_files']} files scanned with {len(scan['issues'])} issues",
        ),
        _check(
            "sandbox_flow_coverage",
            integration["flow_coverage_rate"] == 1.0,
            f"flow coverage rate {integration['flow_coverage_rate']}",
        ),
        _check(
            "incident_idempotency",
            idempotency["same_incident_id"] and idempotency["duplicate_created"] is False,
            "duplicate source event returned the existing incident",
        ),
        _check(
            "signal_idempotency",
            idempotency["duplicate_signal_ignored"] is True,
            "duplicate field signal did not create duplicate state",
        ),
        _check(
            "webhook_retry_behavior",
            retry["final_status"] == "delivered" and retry["attempt_count"] >= 2,
            "local retry attempts reached delivered state without outbound dispatch",
        ),
        _check(
            "restore_idempotency",
            restore["idempotent"] is True and restore["closed_event_count"] == 1,
            "repeated restore preserved a single closure event",
        ),
        _check(
            "timeout_failsafe",
            timeout["timeout_applied"] is True and timeout["reason_code"] == "TIMEOUT_FAILSAFE",
            "ambiguous incident exercised timeout fallback",
        ),
        _check(
            "pilot_report_ready",
            sandbox_summary["report_ready"] is True,
            "closed-loop data and outbox records are available for report generation",
        ),
        _check(
            "scenario_matrix",
            scenario_matrix["failed"] == 0 and scenario_matrix["scenario_count"] >= 7,
            f"{scenario_matrix['passed']}/{scenario_matrix['scenario_count']} scenarios passed",
        ),
        _check(
            "ml_baseline_benchmark",
            ml_benchmark["benchmark_ready"] is True
            and ml_benchmark["public_safe_checks"]["status"] == "passed"
            and ml_benchmark["governance"]["no_model_deployed"] is True,
            f"best policy {ml_benchmark['benchmark_summary']['best_policy_by_mae']} with benchmark-only governance",
        ),
    ]
    sandbox_ready = all(check["status"] == "passed" for check in checks)

    return {
        "report_type": "private-sandbox-readiness-gate",
        "data_boundary": "synthetic-public-safe",
        "readiness": {
            "prototype_ready": True,
            "sandbox_pilot_ready": sandbox_ready,
            "production_ready": False,
            "gate_decision": "ready_for_private_sandbox_discussion" if sandbox_ready else "needs_remediation",
        },
        "passed_checks": [check for check in checks if check["status"] == "passed"],
        "checks": checks,
        "known_gaps": [
            "Production authorization policy",
            "Managed database and migration plan",
            "Managed outbound delivery worker",
            "Receiver-side verification",
            "Replay-window enforcement",
            "Live observability and alert routing",
            "Operational data governance review",
        ],
        "public_safe_scan": {
            "status": scan["status"],
            "scanned_files": scan["scanned_files"],
            "allowed_references": scan["allowed_references"],
            "issues": len(scan["issues"]),
        },
        "scenario_matrix": {
            "scenario_count": scenario_matrix["scenario_count"],
            "passed": scenario_matrix["passed"],
            "failed": scenario_matrix["failed"],
            "public_safe_status": scenario_matrix["public_safe_checks"]["status"],
            "coverage_by_capability": scenario_matrix["coverage_by_capability"],
        },
        "ml_baseline": {
            "benchmark_ready": ml_benchmark["benchmark_ready"],
            "policy_count": len(ml_benchmark["policies"]),
            "best_policy_by_mae": ml_benchmark["benchmark_summary"]["best_policy_by_mae"],
            "rules_first_mae_hours": ml_benchmark["benchmark_summary"].get("rules_first_mae_hours"),
            "best_policy_mae_hours": ml_benchmark["benchmark_summary"].get("best_policy_mae_hours"),
            "public_safe_status": ml_benchmark["public_safe_checks"]["status"],
            "no_model_deployed": ml_benchmark["governance"]["no_model_deployed"],
            "production_ready": ml_benchmark["governance"]["production_ready"],
        },
        "sandbox_integration": {
            "mode": integration["mode"],
            "outbound_http_sent": integration["outbound_http_sent"],
            "flow_coverage_rate": integration["flow_coverage_rate"],
            "retry_delivery_rate": integration["retry_behavior"]["delivery_rate"],
            "retry_attempt_rate": integration["retry_behavior"]["attempt_rate"],
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    readiness = report["readiness"]
    checks = "\n".join(
        f"- {check['name']}: `{check['status']}` - {check['evidence']}" for check in report["checks"]
    )
    gaps = "\n".join(f"- {gap}" for gap in report["known_gaps"])
    integration = report["sandbox_integration"]
    matrix = report["scenario_matrix"]
    ml_baseline = report["ml_baseline"]
    scan = report["public_safe_scan"]
    return f"""# Private Sandbox Readiness Gate

Data boundary: `{report['data_boundary']}`

## Decision

- Prototype ready: `{readiness['prototype_ready']}`
- Sandbox pilot ready: `{readiness['sandbox_pilot_ready']}`
- Production ready: `{readiness['production_ready']}`
- Gate decision: `{readiness['gate_decision']}`

## Checks

{checks}

## Public-Safe Scan

- Status: `{scan['status']}`
- Scanned files: `{scan['scanned_files']}`
- Allowed references: `{scan['allowed_references']}`
- Issues: `{scan['issues']}`

## Scenario Matrix

- Scenario count: `{matrix['scenario_count']}`
- Passed: `{matrix['passed']}`
- Failed: `{matrix['failed']}`
- Public-safe status: `{matrix['public_safe_status']}`

## ML Baseline Benchmark

- Benchmark ready: `{ml_baseline['benchmark_ready']}`
- Policy count: `{ml_baseline['policy_count']}`
- Best policy by MAE: `{ml_baseline['best_policy_by_mae']}`
- Rules-first MAE hours: `{ml_baseline['rules_first_mae_hours']}`
- Best policy MAE hours: `{ml_baseline['best_policy_mae_hours']}`
- Public-safe status: `{ml_baseline['public_safe_status']}`
- No model deployed: `{ml_baseline['no_model_deployed']}`

## Sandbox Integration

- Mode: `{integration['mode']}`
- Outbound HTTP sent: `{integration['outbound_http_sent']}`
- Flow coverage rate: `{integration['flow_coverage_rate']}`
- Retry delivery rate: `{integration['retry_delivery_rate']}`
- Retry attempt rate: `{integration['retry_attempt_rate']}`

## Known Gaps

{gaps}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the private sandbox readiness gate report.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = build_readiness_gate()
    rendered = render_markdown(report) if args.format == "markdown" else json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + ("\n" if not rendered.endswith("\n") else ""), encoding="utf-8")
        return
    print(rendered)
    if not report["readiness"]["sandbox_pilot_ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.exceptions import AccessDeniedError, StateConflictError
from apps.api.services import IncidentService
from scripts.run_partner_sandbox_flow import public_safe_checks

DEFAULT_CATALOG = ROOT / "data" / "synthetic" / "pilot_scenarios.json"


def load_scenario_catalog(path: Path = DEFAULT_CATALOG) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check(name: str, passed: bool, evidence: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "passed" if passed else "failed",
        "evidence": evidence,
    }


def _delivery_for(service: IncidentService, incident_id: str, event_type: str) -> dict[str, Any] | None:
    matches = [
        delivery
        for delivery in service.list_webhook_deliveries()
        if delivery["incident_id"] == incident_id and delivery["event_type"] == event_type
    ]
    return matches[-1] if matches else None


def _event_count(service: IncidentService, incident_id: str, event_type: str) -> int:
    return len([event for event in service.list_events(incident_id) if event["event_type"] == event_type])


def _run_step(
    service: IncidentService,
    scenario: dict[str, Any],
    step: dict[str, Any],
    incident: dict[str, Any] | None,
    state: dict[str, Any],
) -> dict[str, Any] | None:
    if incident is None:
        return None

    step_type = step["type"]
    if step_type == "duplicate_incident":
        duplicate, created = service.create_incident(
            partner_id=scenario["partner_profile"]["partner_id"],
            **scenario["incident"],
        )
        state["duplicate_incident_same"] = duplicate["id"] == incident["id"]
        state["duplicate_incident_created"] = created
        return incident

    if step_type == "field_signal":
        updated, signal = service.add_field_signal(
            incident_id=incident["id"],
            channel=step.get("channel", "FIELD_APP"),
            raw_text=step["raw_text"],
            source_signal_id=step.get("source_signal_id"),
        )
        state["last_signal_id"] = signal["id"]
        state["last_signal_step"] = step
        return updated

    if step_type == "duplicate_signal":
        last_signal_step = state.get("last_signal_step")
        if not last_signal_step:
            state["duplicate_signal_ignored"] = False
            return incident
        updated, duplicate_signal = service.add_field_signal(
            incident_id=incident["id"],
            channel=last_signal_step.get("channel", "FIELD_APP"),
            raw_text=last_signal_step["raw_text"],
            source_signal_id=last_signal_step.get("source_signal_id"),
        )
        state["duplicate_signal_ignored"] = duplicate_signal["id"] == state.get("last_signal_id")
        return updated

    if step_type == "timeout_check":
        service.force_backdate_incident(incident["id"], minutes_ago=step.get("minutes_ago", 121))
        return service.apply_timeout_if_needed(incident["id"])

    if step_type == "restore":
        restored = service.restore_incident(incident["id"], restored_by=step.get("restored_by", "SCADA_SENSOR"))
        state["restore_event_count_after_first"] = _event_count(service, incident["id"], "INCIDENT_CLOSED")
        return restored

    if step_type == "restore_again":
        restored = service.restore_incident(incident["id"], restored_by=step.get("restored_by", "SCADA_SENSOR"))
        state["restore_event_count_after_second"] = _event_count(service, incident["id"], "INCIDENT_CLOSED")
        state["restore_idempotent"] = (
            state.get("restore_event_count_after_first") == state.get("restore_event_count_after_second") == 1
        )
        return restored

    if step_type == "webhook_attempts":
        delivery = _delivery_for(service, incident["id"], step["event_type"])
        state["webhook_event_type"] = step["event_type"]
        if not delivery:
            state["webhook_final_status"] = "missing"
            state["webhook_attempt_count"] = 0
            return incident
        for outcome in step["outcomes"]:
            service.record_webhook_attempt(
                delivery["event_id"],
                outcome=outcome,
                response_status=202 if outcome == "delivered" else 503,
                error_message=None if outcome == "delivered" else "Synthetic partner receiver unavailable",
            )
        updated_delivery = service.get_webhook_delivery(delivery["event_id"])
        state["webhook_final_status"] = updated_delivery["status"]
        state["webhook_attempt_count"] = updated_delivery["attempt_count"]
        return incident

    raise ValueError(f"Unsupported scenario step type: {step_type}")


def _expected_checks(
    service: IncidentService,
    scenario: dict[str, Any],
    incident: dict[str, Any] | None,
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    expected = scenario["expected"]
    checks: list[dict[str, Any]] = []
    create_denied = state.get("create_denied", False)

    if "create_denied" in expected:
        checks.append(_check("create_denied", create_denied == expected["create_denied"], f"create_denied={create_denied}"))
        return checks

    if incident is None:
        return [_check("incident_created", False, "incident was not created")]

    if "final_status" in expected:
        checks.append(_check("final_status", incident["status"] == expected["final_status"], incident["status"]))
    if "reason_code" in expected:
        checks.append(_check("reason_code", incident["reason_code"] == expected["reason_code"], incident["reason_code"]))
    if "eta_hours" in expected:
        checks.append(
            _check(
                "eta_hours",
                incident["current_eta_hours"] == expected["eta_hours"],
                str(incident["current_eta_hours"]),
            )
        )
    if "recommendation" in expected:
        checks.append(
            _check(
                "recommendation",
                incident["dispatch_decision"] == expected["recommendation"],
                incident["dispatch_decision"],
            )
        )
    if "timeout_applied" in expected:
        checks.append(
            _check("timeout_applied", incident["timeout_applied"] == expected["timeout_applied"], str(incident["timeout_applied"]))
        )
    if "duplicate_incident_same" in expected:
        checks.append(
            _check(
                "duplicate_incident_same",
                state.get("duplicate_incident_same") == expected["duplicate_incident_same"],
                str(state.get("duplicate_incident_same")),
            )
        )
    if "duplicate_signal_ignored" in expected:
        checks.append(
            _check(
                "duplicate_signal_ignored",
                state.get("duplicate_signal_ignored") == expected["duplicate_signal_ignored"],
                str(state.get("duplicate_signal_ignored")),
            )
        )
    if "restore_idempotent" in expected:
        checks.append(
            _check(
                "restore_idempotent",
                state.get("restore_idempotent") == expected["restore_idempotent"],
                str(state.get("restore_idempotent")),
            )
        )
    if "closed_dataset_min_rows" in expected:
        rows = service.export_closed_incidents_dataset()
        checks.append(
            _check(
                "closed_dataset_rows",
                len(rows) >= expected["closed_dataset_min_rows"],
                str(len(rows)),
            )
        )
    if "webhook_event_types" in expected:
        event_types = {delivery["event_type"] for delivery in service.list_webhook_deliveries()}
        missing = [event_type for event_type in expected["webhook_event_types"] if event_type not in event_types]
        checks.append(_check("webhook_event_types", not missing, ",".join(sorted(event_types))))
    if "webhook_final_status" in expected:
        checks.append(
            _check(
                "webhook_final_status",
                state.get("webhook_final_status") == expected["webhook_final_status"],
                str(state.get("webhook_final_status")),
            )
        )
    if "webhook_attempt_count" in expected:
        checks.append(
            _check(
                "webhook_attempt_count",
                state.get("webhook_attempt_count") == expected["webhook_attempt_count"],
                str(state.get("webhook_attempt_count")),
            )
        )
    return checks


def run_single_scenario(scenario: dict[str, Any], db_path: Path) -> dict[str, Any]:
    service = IncidentService(db_path=db_path)
    profile = scenario["partner_profile"]
    service.upsert_partner_profile(**profile)

    state: dict[str, Any] = {
        "create_denied": False,
        "outbound_http_sent": False,
    }
    incident: dict[str, Any] | None = None
    error: str | None = None

    try:
        incident, created = service.create_incident(
            partner_id=profile["partner_id"],
            **scenario["incident"],
        )
        state["created"] = created
        for step in scenario["steps"]:
            incident = _run_step(service, scenario, step, incident, state)
    except AccessDeniedError as exc:
        state["create_denied"] = True
        error = "access_denied"
    except StateConflictError as exc:
        error = "state_conflict"

    checks = _expected_checks(service, scenario, incident, state)
    if error and not state["create_denied"]:
        checks.append(_check("unexpected_error", False, error))
    passed = bool(checks) and all(check["status"] == "passed" for check in checks)

    return {
        "scenario_id": scenario["id"],
        "name": scenario["name"],
        "status": "passed" if passed else "failed",
        "capabilities": scenario["capabilities"],
        "checks": checks,
        "evidence": {
            "incident_created": incident is not None,
            "final_status": incident["status"] if incident else None,
            "reason_code": incident["reason_code"] if incident else None,
            "outbound_http_sent": False,
            "create_denied": state["create_denied"],
        },
    }


def run_pilot_scenario_matrix(catalog_path: Path = DEFAULT_CATALOG) -> dict[str, Any]:
    catalog = load_scenario_catalog(catalog_path)
    results = []
    capability_totals: Counter[str] = Counter()
    capability_passed: Counter[str] = Counter()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        for index, scenario in enumerate(catalog["scenarios"], start=1):
            result = run_single_scenario(scenario, Path(tmpdir) / f"scenario-{index}.db")
            results.append(result)
            for capability in scenario["capabilities"]:
                capability_totals[capability] += 1
                if result["status"] == "passed":
                    capability_passed[capability] += 1

    coverage_by_capability = {
        capability: {
            "scenarios": capability_totals[capability],
            "passed": capability_passed[capability],
        }
        for capability in sorted(capability_totals)
    }
    passed_count = len([result for result in results if result["status"] == "passed"])
    summary = {
        "report_type": "pilot-scenario-matrix",
        "data_boundary": catalog["data_boundary"],
        "catalog_version": catalog["version"],
        "scenario_count": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "coverage_by_capability": coverage_by_capability,
        "scenario_results": results,
    }
    summary["public_safe_checks"] = public_safe_checks(summary)
    return summary


def render_markdown(report: dict[str, Any]) -> str:
    capability_lines = "\n".join(
        f"- {capability}: `{values['passed']}/{values['scenarios']}`"
        for capability, values in report["coverage_by_capability"].items()
    )
    scenario_lines = "\n".join(
        f"- {result['scenario_id']}: `{result['status']}` ({', '.join(result['capabilities'])})"
        for result in report["scenario_results"]
    )
    return f"""# Pilot Scenario Matrix

Data boundary: `{report['data_boundary']}`
Catalog version: `{report['catalog_version']}`

## Summary

- Scenario count: `{report['scenario_count']}`
- Passed: `{report['passed']}`
- Failed: `{report['failed']}`
- Public-safe checks: `{report['public_safe_checks']['status']}`

## Capability Coverage

{capability_lines}

## Scenario Results

{scenario_lines}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the synthetic pilot scenario matrix.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = run_pilot_scenario_matrix(args.catalog)
    rendered = render_markdown(report) if args.format == "markdown" else json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + ("\n" if not rendered.endswith("\n") else ""), encoding="utf-8")
        return
    print(rendered)
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

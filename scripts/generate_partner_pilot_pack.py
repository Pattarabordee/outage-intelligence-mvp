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

from scripts.generate_readiness_gate import build_readiness_gate
from scripts.run_partner_sandbox_flow import public_safe_checks
from scripts.run_shadow_evaluation_protocol import build_shadow_evaluation_protocol

DEFAULT_CHECKLIST = ROOT / "data" / "synthetic" / "partner_pilot_onboarding_checklist.json"


def load_onboarding_checklist(path: Path = DEFAULT_CHECKLIST) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten_checklist(checklist: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item | {"section": section["section"]}
        for section in checklist["checklist"]
        for item in section["items"]
    ]


def _check(name: str, passed: bool, evidence: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "passed" if passed else "needs_review",
        "evidence": evidence,
    }


def _summarize_onboarding(checklist: dict[str, Any]) -> dict[str, Any]:
    items = _flatten_checklist(checklist)
    status_counts = Counter(item["status"] for item in items)
    required_items = [item for item in items if item["required_for_private_sandbox"]]
    required_ready = [
        item
        for item in required_items
        if item["status"] in {"ready_for_discussion", "needs_private_pilot_input", "production_gap"}
    ]
    return {
        "version": checklist["version"],
        "section_count": len(checklist["checklist"]),
        "item_count": len(items),
        "required_item_count": len(required_items),
        "required_items_accounted_for": len(required_ready) == len(required_items),
        "status_counts": dict(status_counts),
        "needs_private_pilot_input": [
            {"id": item["id"], "section": item["section"], "name": item["name"]}
            for item in items
            if item["status"] == "needs_private_pilot_input"
        ],
        "production_gaps": [
            {"id": item["id"], "section": item["section"], "name": item["name"]}
            for item in items
            if item["status"] == "production_gap"
        ],
    }


def _build_acceptance_checks(
    readiness_gate: dict[str, Any],
    shadow_evaluation: dict[str, Any],
    onboarding_summary: dict[str, Any],
    base_report: dict[str, Any],
) -> list[dict[str, Any]]:
    scan = public_safe_checks(base_report)
    return [
        _check(
            "readiness_gate",
            readiness_gate["readiness"]["sandbox_pilot_ready"] is True
            and readiness_gate["readiness"]["production_ready"] is False,
            readiness_gate["readiness"]["gate_decision"],
        ),
        _check(
            "scenario_matrix",
            readiness_gate["scenario_matrix"]["failed"] == 0,
            f"{readiness_gate['scenario_matrix']['passed']}/{readiness_gate['scenario_matrix']['scenario_count']} scenarios passed",
        ),
        _check(
            "shadow_evaluation",
            shadow_evaluation["shadow_evaluation_ready"] is True
            and shadow_evaluation["governance"]["production_ready"] is False,
            f"{shadow_evaluation['contract_validation']['rows']} synthetic rows validated",
        ),
        _check(
            "onboarding_checklist",
            onboarding_summary["required_items_accounted_for"] is True,
            f"{onboarding_summary['required_item_count']} required items accounted for",
        ),
        _check(
            "public_safe_output",
            scan["status"] == "passed",
            scan["status"],
        ),
    ]


def build_partner_pilot_pack(
    root: Path = ROOT,
    checklist: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checklist = checklist if checklist is not None else load_onboarding_checklist()
    onboarding_summary = _summarize_onboarding(checklist)
    readiness_gate = build_readiness_gate(root=root)
    shadow_evaluation = build_shadow_evaluation_protocol()

    base_report: dict[str, Any] = {
        "report_type": "partner-pilot-onboarding-pack",
        "data_boundary": checklist["data_boundary"],
        "pack_version": "partner-pilot-pack-v1",
        "readiness_decision": {
            "prototype_ready": readiness_gate["readiness"]["prototype_ready"],
            "sandbox_pilot_ready": readiness_gate["readiness"]["sandbox_pilot_ready"],
            "production_ready": False,
            "gate_decision": readiness_gate["readiness"]["gate_decision"],
            "recommended_decision": "proceed_to_private_sandbox_planning",
        },
        "pilot_scope": checklist["pilot_scope"],
        "onboarding": onboarding_summary,
        "governance": {
            "scope": "private_sandbox_discussion",
            "synthetic_data_only": True,
            "no_live_partner_dispatch": True,
            "no_outbound_network_delivery": True,
            "no_model_deployed": True,
            "production_ready": False,
            "requires_private_review_before_live_use": True,
        },
        "readiness_evidence": {
            "public_safe_scan_status": readiness_gate["public_safe_scan"]["status"],
            "scenario_matrix_failed": readiness_gate["scenario_matrix"]["failed"],
            "sandbox_flow_coverage_rate": readiness_gate["sandbox_integration"]["flow_coverage_rate"],
            "ml_baseline_ready": readiness_gate["ml_baseline"]["benchmark_ready"],
            "shadow_evaluation_ready": readiness_gate["shadow_evaluation"]["shadow_evaluation_ready"],
        },
        "shadow_evaluation": {
            "protocol_version": shadow_evaluation["protocol_version"],
            "contract_version": shadow_evaluation["contract_version"],
            "rows": shadow_evaluation["contract_validation"]["rows"],
            "required_field_coverage": shadow_evaluation["contract_validation"]["required_field_coverage"],
            "feature_snapshot_coverage": shadow_evaluation["contract_validation"]["feature_snapshot_coverage"],
            "best_policy_by_mae": shadow_evaluation["benchmark_summary"]["best_policy_by_mae"],
            "production_ready": shadow_evaluation["governance"]["production_ready"],
        },
        "raci": checklist["raci"],
        "risk_register": checklist["risk_register"],
        "go_no_go": {
            "go_criteria": checklist["go_criteria"],
            "no_go_criteria": checklist["no_go_criteria"],
        },
        "next_actions": [
            "Confirm utility and partner pilot owners.",
            "Agree partner class, synthetic site scope, and NOC review path.",
            "Run the onboarding pack beside the readiness gate and pilot evidence report.",
            "Review retention, de-identification, and access expectations before private data is introduced.",
            "Design a private implementation plan for authorization, tenant boundary, delivery worker, and live observability.",
        ],
    }
    acceptance_checks = _build_acceptance_checks(
        readiness_gate=readiness_gate,
        shadow_evaluation=shadow_evaluation,
        onboarding_summary=onboarding_summary,
        base_report=base_report,
    )
    base_report["acceptance_checks"] = acceptance_checks
    base_report["public_safe_checks"] = public_safe_checks(base_report)
    base_report["pack_ready"] = all(check["status"] == "passed" for check in acceptance_checks)
    return base_report


def render_markdown(report: dict[str, Any]) -> str:
    readiness = report["readiness_decision"]
    onboarding = report["onboarding"]
    evidence = report["readiness_evidence"]
    shadow = report["shadow_evaluation"]
    governance = report["governance"]
    checks = "\n".join(
        f"- {check['name']}: `{check['status']}` - {check['evidence']}" for check in report["acceptance_checks"]
    )
    needs_input = "\n".join(
        f"- {item['id']} ({item['section']}): {item['name']}"
        for item in onboarding["needs_private_pilot_input"]
    )
    if not needs_input:
        needs_input = "- None."
    production_gaps = "\n".join(
        f"- {item['id']} ({item['section']}): {item['name']}" for item in onboarding["production_gaps"]
    )
    if not production_gaps:
        production_gaps = "- None."
    risks = "\n".join(
        f"- {risk['id']} ({risk['area']}): {risk['risk']} Mitigation: {risk['mitigation']}"
        for risk in report["risk_register"]
    )
    go_criteria = "\n".join(f"- {item}" for item in report["go_no_go"]["go_criteria"])
    no_go_criteria = "\n".join(f"- {item}" for item in report["go_no_go"]["no_go_criteria"])
    next_actions = "\n".join(f"- {item}" for item in report["next_actions"])
    return f"""# Partner Pilot Onboarding Pack

Data boundary: `{report['data_boundary']}`
Pack version: `{report['pack_version']}`
Pack ready: `{report['pack_ready']}`

## Readiness Decision

- Prototype ready: `{readiness['prototype_ready']}`
- Sandbox pilot ready: `{readiness['sandbox_pilot_ready']}`
- Production ready: `{readiness['production_ready']}`
- Gate decision: `{readiness['gate_decision']}`
- Recommended decision: `{readiness['recommended_decision']}`

## Acceptance Checks

{checks}

## Onboarding Checklist

- Sections: `{onboarding['section_count']}`
- Items: `{onboarding['item_count']}`
- Required items: `{onboarding['required_item_count']}`
- Required items accounted for: `{onboarding['required_items_accounted_for']}`
- Status counts: `{onboarding['status_counts']}`

Private pilot input still needed:

{needs_input}

Production gaps:

{production_gaps}

## Governance Boundary

- Scope: `{governance['scope']}`
- Synthetic data only: `{governance['synthetic_data_only']}`
- No live partner dispatch: `{governance['no_live_partner_dispatch']}`
- No outbound network delivery: `{governance['no_outbound_network_delivery']}`
- No model deployed: `{governance['no_model_deployed']}`
- Production ready: `{governance['production_ready']}`

## Readiness Evidence

- Public-safe scan status: `{evidence['public_safe_scan_status']}`
- Scenario matrix failed: `{evidence['scenario_matrix_failed']}`
- Sandbox flow coverage rate: `{evidence['sandbox_flow_coverage_rate']}`
- ML baseline ready: `{evidence['ml_baseline_ready']}`
- Shadow evaluation ready: `{evidence['shadow_evaluation_ready']}`

## Shadow Evaluation

- Protocol version: `{shadow['protocol_version']}`
- Contract version: `{shadow['contract_version']}`
- Rows: `{shadow['rows']}`
- Required field coverage: `{shadow['required_field_coverage']}`
- Feature snapshot coverage: `{shadow['feature_snapshot_coverage']}`
- Best policy by MAE: `{shadow['best_policy_by_mae']}`
- Production ready: `{shadow['production_ready']}`

## Risk Register

{risks}

## Go Criteria

{go_criteria}

## No-Go Criteria

{no_go_criteria}

## Next Actions

{next_actions}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a public-safe partner pilot onboarding pack.")
    parser.add_argument("--checklist", type=Path, default=DEFAULT_CHECKLIST)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = build_partner_pilot_pack(checklist=load_onboarding_checklist(args.checklist))
    rendered = render_markdown(report) if args.format == "markdown" else json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + ("\n" if not rendered.endswith("\n") else ""), encoding="utf-8")
        return
    print(rendered)
    if not report["pack_ready"] or report["public_safe_checks"]["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

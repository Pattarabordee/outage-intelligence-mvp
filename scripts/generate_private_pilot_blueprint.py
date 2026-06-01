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

from scripts.generate_partner_pilot_pack import build_partner_pilot_pack
from scripts.run_partner_sandbox_flow import public_safe_checks

DEFAULT_BLUEPRINT = ROOT / "data" / "synthetic" / "private_pilot_implementation_blueprint.json"


def load_blueprint(path: Path = DEFAULT_BLUEPRINT) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check(name: str, passed: bool, evidence: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "passed" if passed else "needs_review",
        "evidence": evidence,
    }


def _summarize_workstreams(blueprint: dict[str, Any]) -> dict[str, Any]:
    workstreams = blueprint["workstreams"]
    owner_counts = Counter(workstream["owner_role"] for workstream in workstreams)
    private_build_required = [
        workstream["id"]
        for workstream in workstreams
        if "private" in workstream["private_pilot_requirement"].lower()
        or "managed" in workstream["private_pilot_requirement"].lower()
        or "approve" in workstream["private_pilot_requirement"].lower()
    ]
    return {
        "workstream_count": len(workstreams),
        "owner_role_counts": dict(owner_counts),
        "private_build_required_count": len(private_build_required),
        "private_build_required_ids": private_build_required,
        "all_workstreams_have_private_requirement": all(
            bool(workstream.get("private_pilot_requirement")) for workstream in workstreams
        ),
        "all_workstreams_have_production_gate": all(
            bool(workstream.get("production_gate")) for workstream in workstreams
        ),
    }


def _summarize_maturity(blueprint: dict[str, Any]) -> dict[str, Any]:
    stages = blueprint["maturity_stages"]
    return {
        "stage_count": len(stages),
        "stages": [stage["stage"] for stage in stages],
        "status_by_stage": {stage["stage"]: stage["status"] for stage in stages},
        "private_pilot_status": next(
            stage["status"] for stage in stages if stage["stage"] == "private_pilot"
        ),
        "production_status": next(stage["status"] for stage in stages if stage["stage"] == "production"),
    }


def _build_acceptance_checks(
    blueprint: dict[str, Any],
    partner_pack: dict[str, Any],
    workstream_summary: dict[str, Any],
    maturity_summary: dict[str, Any],
    base_report: dict[str, Any],
) -> list[dict[str, Any]]:
    thresholds = blueprint["acceptance_thresholds"]
    required_stages = set(thresholds["required_maturity_stages"])
    actual_stages = set(maturity_summary["stages"])
    release_gates = blueprint["deployment_plan"]["release_gates"]
    private_controls = blueprint["security_model"]["required_private_controls"]
    scan = public_safe_checks(base_report)

    return [
        _check(
            "partner_pilot_pack",
            partner_pack["pack_ready"] is True and partner_pack["readiness_decision"]["production_ready"] is False,
            f"pack_ready={partner_pack['pack_ready']}",
        ),
        _check(
            "maturity_stage_coverage",
            required_stages.issubset(actual_stages),
            f"{len(actual_stages)} stages documented",
        ),
        _check(
            "workstream_coverage",
            workstream_summary["workstream_count"] >= thresholds["minimum_workstreams"]
            and workstream_summary["all_workstreams_have_private_requirement"]
            and workstream_summary["all_workstreams_have_production_gate"],
            f"{workstream_summary['workstream_count']} workstreams documented",
        ),
        _check(
            "security_controls",
            len(private_controls) >= thresholds["required_private_controls"],
            f"{len(private_controls)} private controls documented",
        ),
        _check(
            "release_gates",
            len(release_gates) >= thresholds["required_release_gates"],
            f"{len(release_gates)} release gates documented",
        ),
        _check(
            "not_production_ready",
            maturity_summary["production_status"] == "not_ready",
            maturity_summary["production_status"],
        ),
        _check(
            "public_safe_output",
            scan["status"] == "passed",
            scan["status"],
        ),
    ]


def build_private_pilot_blueprint_report(
    root: Path = ROOT,
    blueprint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blueprint = blueprint if blueprint is not None else load_blueprint()
    partner_pack = build_partner_pilot_pack(root=root)
    workstream_summary = _summarize_workstreams(blueprint)
    maturity_summary = _summarize_maturity(blueprint)

    base_report: dict[str, Any] = {
        "report_type": "private-pilot-implementation-blueprint",
        "data_boundary": blueprint["data_boundary"],
        "blueprint_version": blueprint["version"],
        "capability": blueprint["capability"],
        "implementation_decision": {
            "recommended_next_step": "private_pilot_architecture_review",
            "prototype_ready": partner_pack["readiness_decision"]["prototype_ready"],
            "sandbox_pilot_ready": partner_pack["readiness_decision"]["sandbox_pilot_ready"],
            "private_pilot_ready": False,
            "production_ready": False,
            "rationale": "The public prototype has strong sandbox evidence, but private pilot operation requires private controls, managed infrastructure, and governance approval.",
        },
        "maturity": maturity_summary,
        "workstream_summary": workstream_summary,
        "workstreams": blueprint["workstreams"],
        "api_contract_boundary": blueprint["api_contract_boundary"],
        "security_model": blueprint["security_model"],
        "observability_model": blueprint["observability_model"],
        "deployment_plan": blueprint["deployment_plan"],
        "open_decisions": blueprint["open_decisions"],
        "partner_pack_evidence": {
            "pack_ready": partner_pack["pack_ready"],
            "gate_decision": partner_pack["readiness_decision"]["gate_decision"],
            "public_safe_status": partner_pack["public_safe_checks"]["status"],
            "scenario_matrix_failed": partner_pack["readiness_evidence"]["scenario_matrix_failed"],
            "shadow_evaluation_ready": partner_pack["readiness_evidence"]["shadow_evaluation_ready"],
        },
        "non_goals": blueprint["non_goals"],
    }
    acceptance_checks = _build_acceptance_checks(
        blueprint=blueprint,
        partner_pack=partner_pack,
        workstream_summary=workstream_summary,
        maturity_summary=maturity_summary,
        base_report=base_report,
    )
    base_report["acceptance_checks"] = acceptance_checks
    base_report["public_safe_checks"] = public_safe_checks(base_report)
    base_report["blueprint_ready"] = all(check["status"] == "passed" for check in acceptance_checks)
    return base_report


def render_markdown(report: dict[str, Any]) -> str:
    decision = report["implementation_decision"]
    maturity = report["maturity"]
    workstream_summary = report["workstream_summary"]
    partner_evidence = report["partner_pack_evidence"]
    checks = "\n".join(
        f"- {check['name']}: `{check['status']}` - {check['evidence']}" for check in report["acceptance_checks"]
    )
    stages = "\n".join(
        f"- {stage}: `{status}`" for stage, status in maturity["status_by_stage"].items()
    )
    workstreams = "\n".join(
        f"- {item['id']} {item['name']}: {item['private_pilot_requirement']}"
        for item in report["workstreams"]
    )
    security_controls = "\n".join(
        f"- {item}" for item in report["security_model"]["required_private_controls"]
    )
    metrics = "\n".join(f"- {item}" for item in report["observability_model"]["metrics"])
    release_gates = "\n".join(f"- {item}" for item in report["deployment_plan"]["release_gates"])
    open_decisions = "\n".join(
        f"- {item['id']}: {item['decision']} Owner: {item['owner_role']}"
        for item in report["open_decisions"]
    )
    non_goals = "\n".join(f"- {item}" for item in report["non_goals"])
    return f"""# Private Pilot Implementation Blueprint

Data boundary: `{report['data_boundary']}`
Blueprint version: `{report['blueprint_version']}`
Blueprint ready: `{report['blueprint_ready']}`

## Implementation Decision

- Recommended next step: `{decision['recommended_next_step']}`
- Prototype ready: `{decision['prototype_ready']}`
- Sandbox pilot ready: `{decision['sandbox_pilot_ready']}`
- Private pilot ready: `{decision['private_pilot_ready']}`
- Production ready: `{decision['production_ready']}`
- Rationale: {decision['rationale']}

## Acceptance Checks

{checks}

## Maturity Stages

{stages}

## Workstream Summary

- Workstreams: `{workstream_summary['workstream_count']}`
- Private build required: `{workstream_summary['private_build_required_count']}`
- All workstreams have private requirements: `{workstream_summary['all_workstreams_have_private_requirement']}`
- All workstreams have production gates: `{workstream_summary['all_workstreams_have_production_gate']}`

{workstreams}

## Partner Pack Evidence

- Pack ready: `{partner_evidence['pack_ready']}`
- Gate decision: `{partner_evidence['gate_decision']}`
- Public-safe status: `{partner_evidence['public_safe_status']}`
- Scenario matrix failed: `{partner_evidence['scenario_matrix_failed']}`
- Shadow evaluation ready: `{partner_evidence['shadow_evaluation_ready']}`

## Security Model

{security_controls}

## Observability Model

{metrics}

## Deployment And Release Gates

{release_gates}

## Open Decisions

{open_decisions}

## Non-Goals

{non_goals}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the public-safe private pilot implementation blueprint.")
    parser.add_argument("--blueprint", type=Path, default=DEFAULT_BLUEPRINT)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = build_private_pilot_blueprint_report(blueprint=load_blueprint(args.blueprint))
    rendered = render_markdown(report) if args.format == "markdown" else json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + ("\n" if not rendered.endswith("\n") else ""), encoding="utf-8")
        return
    print(rendered)
    if not report["blueprint_ready"] or report["public_safe_checks"]["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_ml_baseline_benchmark import build_ml_baseline_benchmark
from scripts.run_partner_sandbox_flow import public_safe_checks

DEFAULT_CONTRACT = ROOT / "data" / "synthetic" / "pilot_data_contract.json"
DEFAULT_DATASET = ROOT / "data" / "synthetic" / "shadow_eval_closed_incidents.jsonl"
PROLONGED_THRESHOLD_HOURS = 4.0


def load_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(path: Path = DEFAULT_DATASET) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _rate(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def _check(name: str, passed: bool, evidence: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "passed" if passed else "needs_review",
        "evidence": evidence,
    }


def _required_field_coverage(rows: list[dict[str, Any]], fields: list[str]) -> tuple[float, list[str]]:
    if not rows:
        return 0.0, fields

    present = 0
    missing: set[str] = set()
    for row in rows:
        for field in fields:
            if field in row:
                present += 1
            else:
                missing.add(field)
    return _rate(present, len(rows) * len(fields)), sorted(missing)


def _feature_field_coverage(rows: list[dict[str, Any]], fields: list[str]) -> tuple[float, list[str]]:
    if not rows:
        return 0.0, fields

    present = 0
    missing: set[str] = set()
    for row in rows:
        snapshot = row.get("feature_snapshot", {})
        for field in fields:
            if field in snapshot:
                present += 1
            else:
                missing.add(field)
    return _rate(present, len(rows) * len(fields)), sorted(missing)


def _invalid_values(rows: list[dict[str, Any]], feature_name: str, allowed: list[str]) -> list[str]:
    allowed_set = set(allowed)
    values = {
        str(row.get("feature_snapshot", {}).get(feature_name))
        for row in rows
        if row.get("feature_snapshot", {}).get(feature_name) not in allowed_set
    }
    return sorted(value for value in values if value and value != "None")


def _distinct_feature_values(rows: list[dict[str, Any]], feature_name: str) -> set[str]:
    return {str(row.get("feature_snapshot", {}).get(feature_name)) for row in rows}


def _validate_contract(rows: list[dict[str, Any]], contract: dict[str, Any]) -> dict[str, Any]:
    required_coverage, missing_required = _required_field_coverage(rows, contract["required_fields"])
    feature_coverage, missing_features = _feature_field_coverage(rows, contract["feature_snapshot_required"])
    partner_classes = _distinct_feature_values(rows, "partner_class")
    scada_statuses = _distinct_feature_values(rows, "scada_status")
    prolonged_cases = [
        row for row in rows if float(row["actual_restoration_duration_hours"]) >= PROLONGED_THRESHOLD_HOURS
    ]
    allowed_values = contract["allowed_values"]

    return {
        "rows": len(rows),
        "required_field_coverage": required_coverage,
        "missing_required_fields": missing_required,
        "feature_snapshot_coverage": feature_coverage,
        "missing_feature_snapshot_fields": missing_features,
        "partner_class_count": len(partner_classes),
        "scada_status_count": len(scada_statuses),
        "prolonged_case_count": len(prolonged_cases),
        "invalid_partner_classes": _invalid_values(rows, "partner_class", allowed_values["partner_class"]),
        "invalid_scada_statuses": _invalid_values(rows, "scada_status", allowed_values["scada_status"]),
    }


def _acceptance_checks(
    contract: dict[str, Any],
    validation: dict[str, Any],
    benchmark: dict[str, Any],
) -> list[dict[str, Any]]:
    thresholds = contract["acceptance_thresholds"]
    controls = contract["shadow_controls"]
    checks = [
        _check(
            "data_boundary",
            contract["data_boundary"] == "synthetic-public-safe",
            contract["data_boundary"],
        ),
        _check(
            "minimum_rows",
            validation["rows"] >= thresholds["minimum_rows"],
            f"{validation['rows']} rows >= {thresholds['minimum_rows']}",
        ),
        _check(
            "required_field_coverage",
            validation["required_field_coverage"] >= thresholds["required_field_coverage"],
            f"{validation['required_field_coverage']} coverage",
        ),
        _check(
            "feature_snapshot_coverage",
            validation["feature_snapshot_coverage"] >= thresholds["feature_snapshot_coverage"],
            f"{validation['feature_snapshot_coverage']} coverage",
        ),
        _check(
            "allowed_partner_class_values",
            not validation["invalid_partner_classes"],
            ",".join(validation["invalid_partner_classes"]) or "all values allowed",
        ),
        _check(
            "allowed_scada_status_values",
            not validation["invalid_scada_statuses"],
            ",".join(validation["invalid_scada_statuses"]) or "all values allowed",
        ),
        _check(
            "minimum_partner_classes",
            validation["partner_class_count"] >= thresholds["minimum_partner_classes"],
            f"{validation['partner_class_count']} classes >= {thresholds['minimum_partner_classes']}",
        ),
        _check(
            "minimum_scada_statuses",
            validation["scada_status_count"] >= thresholds["minimum_scada_statuses"],
            f"{validation['scada_status_count']} statuses >= {thresholds['minimum_scada_statuses']}",
        ),
        _check(
            "minimum_prolonged_cases",
            validation["prolonged_case_count"] >= thresholds["minimum_prolonged_cases"],
            f"{validation['prolonged_case_count']} cases >= {thresholds['minimum_prolonged_cases']}",
        ),
        _check(
            "baseline_policy_set",
            benchmark["benchmark_ready"] is True and len(benchmark["policies"]) >= 4,
            f"{len(benchmark['policies'])} policies available",
        ),
        _check(
            "shadow_controls",
            all(controls.values()),
            "benchmark only, no deployed model, no outbound dispatch, no production decision automation",
        ),
        _check(
            "model_governance",
            benchmark["governance"]["no_model_deployed"] is True
            and benchmark["governance"]["production_ready"] is False,
            "benchmark evidence only; no model deployed",
        ),
    ]
    return checks


def build_shadow_evaluation_protocol(
    rows: list[dict[str, Any]] | None = None,
    contract: dict[str, Any] | None = None,
    input_label: str = "data/synthetic/shadow_eval_closed_incidents.jsonl",
) -> dict[str, Any]:
    rows = rows if rows is not None else load_rows(DEFAULT_DATASET)
    contract = contract if contract is not None else load_contract(DEFAULT_CONTRACT)
    validation = _validate_contract(rows, contract)
    benchmark = build_ml_baseline_benchmark(rows=rows, input_label=input_label, test_size=0.25)
    checks = _acceptance_checks(contract, validation, benchmark)

    base_report = {
        "report_type": "pilot-shadow-evaluation-protocol",
        "data_boundary": contract["data_boundary"],
        "protocol_version": "shadow-eval-v1",
        "source_dataset": input_label,
        "contract_version": contract["version"],
        "shadow_evaluation_ready": False,
        "dataset_contract": {
            "required_fields": contract["required_fields"],
            "feature_snapshot_required": contract["feature_snapshot_required"],
            "acceptance_thresholds": contract["acceptance_thresholds"],
        },
        "contract_validation": validation,
        "acceptance_checks": checks,
        "benchmark_summary": benchmark["benchmark_summary"],
        "decision_policy_evidence": benchmark["decision_policy_evidence"],
        "shadow_protocol": {
            "mode": "offline_synthetic_shadow_evaluation",
            "compares_against": ["rules_initial_eta", "global_mean_duration", "scada_status_group_mean", "partner_class_group_mean"],
            "operational_effect": "none",
            "promotion_rule": "Do not change partner-facing ETA policy until private sandbox shadow metrics are reviewed.",
        },
        "governance": {
            "benchmark_only": True,
            "no_model_deployed": True,
            "production_ready": False,
            "known_gaps": [
                "Private sandbox data access agreement",
                "Partner-approved retention and de-identification rules",
                "Shadow-vs-live comparison on governed pilot data",
                "Operator review of underestimation and prolonged-outage cases",
            ],
        },
    }
    scan = public_safe_checks(base_report)
    checks.append(
        _check(
            "public_safe_output",
            scan["status"] == "passed",
            scan["status"],
        )
    )
    ready = all(check["status"] == "passed" for check in checks)
    base_report["shadow_evaluation_ready"] = ready
    base_report["passed_checks"] = [check for check in checks if check["status"] == "passed"]
    base_report["public_safe_checks"] = public_safe_checks(base_report)
    return base_report


def render_markdown(report: dict[str, Any]) -> str:
    validation = report["contract_validation"]
    benchmark = report["benchmark_summary"]
    checks = "\n".join(
        f"- {check['name']}: `{check['status']}` - {check['evidence']}" for check in report["acceptance_checks"]
    )
    gaps = "\n".join(f"- {gap}" for gap in report["governance"]["known_gaps"])
    return f"""# Pilot Shadow Evaluation Protocol

Data boundary: `{report['data_boundary']}`
Protocol version: `{report['protocol_version']}`
Shadow evaluation ready: `{report['shadow_evaluation_ready']}`

## Dataset Contract

- Source dataset: `{report['source_dataset']}`
- Contract version: `{report['contract_version']}`
- Rows: `{validation['rows']}`
- Required field coverage: `{validation['required_field_coverage']}`
- Feature snapshot coverage: `{validation['feature_snapshot_coverage']}`
- Partner classes: `{validation['partner_class_count']}`
- SCADA statuses: `{validation['scada_status_count']}`
- Prolonged cases: `{validation['prolonged_case_count']}`

## Acceptance Checks

{checks}

## Benchmark Summary

- Primary metric: `{benchmark['primary_metric']}`
- Best policy by MAE: `{benchmark['best_policy_by_mae']}`
- Rules-first MAE hours: `{benchmark.get('rules_first_mae_hours')}`
- Best policy MAE hours: `{benchmark.get('best_policy_mae_hours')}`
- Interpretation: {benchmark['interpretation']}

## Protocol Controls

- Mode: `{report['shadow_protocol']['mode']}`
- Operational effect: `{report['shadow_protocol']['operational_effect']}`
- Promotion rule: {report['shadow_protocol']['promotion_rule']}

## Known Gaps

{gaps}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the public-safe pilot shadow evaluation protocol.")
    parser.add_argument("--input", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = build_shadow_evaluation_protocol(
        rows=load_rows(args.input),
        contract=load_contract(args.contract),
        input_label=_display_path(args.input),
    )
    rendered = render_markdown(report) if args.format == "markdown" else json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + ("\n" if not rendered.endswith("\n") else ""), encoding="utf-8")
        return
    print(rendered)
    if not report["shadow_evaluation_ready"] or report["public_safe_checks"]["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

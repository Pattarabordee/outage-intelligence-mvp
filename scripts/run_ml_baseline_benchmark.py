from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.rules import recommendation_from_eta
from scripts.run_partner_sandbox_flow import public_safe_checks

DEFAULT_DATASET = ROOT / "data" / "synthetic" / "closed_incidents.jsonl"
MINIMUM_BENCHMARK_ROWS = 4


def load_rows(path: Path = DEFAULT_DATASET) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _rate(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def _round(value: float) -> float:
    return round(value, 3)


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _feature(row: dict[str, Any], key: str, fallback: str = "unknown") -> str:
    return str(row.get("feature_snapshot", {}).get(key) or fallback)


def _chronological_split(rows: list[dict[str, Any]], test_size: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = sorted(rows, key=lambda row: row.get("prediction_time", ""))
    split_index = int(len(ordered) * (1 - test_size))
    split_index = max(1, min(split_index, len(ordered) - 1))
    return ordered[:split_index], ordered[split_index:]


def _mean_duration(rows: list[dict[str, Any]]) -> float:
    return statistics.fmean(float(row["actual_restoration_duration_hours"]) for row in rows)


def _group_means(rows: list[dict[str, Any]], key_fn: Callable[[dict[str, Any]], str]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[key_fn(row)].append(float(row["actual_restoration_duration_hours"]))
    return {key: statistics.fmean(values) for key, values in grouped.items()}


def _prolonged_metrics(predictions: list[dict[str, Any]], threshold_hours: float) -> dict[str, Any]:
    actual_positive = [
        item for item in predictions if item["actual_restoration_duration_hours"] >= threshold_hours
    ]
    predicted_positive = [item for item in predictions if item["predicted_eta_hours"] >= threshold_hours]
    true_positive = [
        item
        for item in predictions
        if item["actual_restoration_duration_hours"] >= threshold_hours
        and item["predicted_eta_hours"] >= threshold_hours
    ]
    false_positive = [
        item
        for item in predictions
        if item["actual_restoration_duration_hours"] < threshold_hours
        and item["predicted_eta_hours"] >= threshold_hours
    ]

    precision = _rate(len(true_positive), len(predicted_positive))
    recall = _rate(len(true_positive), len(actual_positive))
    f1 = round((2 * precision * recall) / (precision + recall), 3) if precision + recall else 0.0
    return {
        "threshold_hours": threshold_hours,
        "actual_positive": len(actual_positive),
        "predicted_positive": len(predicted_positive),
        "false_positive": len(false_positive),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "predicted_positive_rate": _rate(len(predicted_positive), len(predictions)),
    }


def _evaluate_policy(
    name: str,
    label: str,
    model_family: str,
    uses_training_data: bool,
    prediction_fn: Callable[[dict[str, Any]], float],
    test_rows: list[dict[str, Any]],
    prolonged_threshold_hours: float,
) -> dict[str, Any]:
    predictions = []
    errors = []
    signed_errors = []
    underestimates = 0
    overestimates = 0
    within_one_hour = 0
    actions: Counter[str] = Counter()

    for row in test_rows:
        actual = float(row["actual_restoration_duration_hours"])
        predicted = float(prediction_fn(row))
        signed_error = predicted - actual
        signed_errors.append(signed_error)
        errors.append(abs(signed_error))
        if signed_error < 0:
            underestimates += 1
        if signed_error > 0:
            overestimates += 1
        if abs(signed_error) <= 1:
            within_one_hour += 1
        actions[recommendation_from_eta(predicted)] += 1
        predictions.append(
            {
                "incident_id": row["incident_id"],
                "actual_restoration_duration_hours": actual,
                "predicted_eta_hours": predicted,
            }
        )

    return {
        "name": name,
        "label": label,
        "model_family": model_family,
        "uses_training_data": uses_training_data,
        "test_rows": len(test_rows),
        "mae_hours": _round(statistics.fmean(errors)),
        "mean_error_hours": _round(statistics.fmean(signed_errors)),
        "underestimation_rate": _rate(underestimates, len(test_rows)),
        "overestimation_rate": _rate(overestimates, len(test_rows)),
        "within_one_hour_rate": _rate(within_one_hour, len(test_rows)),
        "prolonged_outage": _prolonged_metrics(predictions, prolonged_threshold_hours),
        "partner_action_distribution": dict(actions),
    }


def _insufficient_rows_report(
    rows: list[dict[str, Any]],
    input_label: str,
    prolonged_threshold_hours: float,
) -> dict[str, Any]:
    report = {
        "report_type": "ml-baseline-benchmark",
        "data_boundary": "synthetic-public-safe",
        "benchmark_ready": False,
        "source_dataset": input_label,
        "dataset": {
            "rows": len(rows),
            "minimum_rows": MINIMUM_BENCHMARK_ROWS,
            "train_rows": 0,
            "test_rows": 0,
            "split_strategy": "chronological_holdout",
            "prolonged_threshold_hours": prolonged_threshold_hours,
        },
        "policies": {},
        "benchmark_summary": {
            "primary_metric": "mae_hours",
            "best_policy_by_mae": None,
            "rules_first_policy": "rules_initial_eta",
            "interpretation": "Insufficient synthetic closed incidents for a holdout benchmark.",
        },
        "decision_policy_evidence": {
            "benchmark_only": True,
            "recommended_next_step": "Add more synthetic closed incidents before comparing ETA policies.",
        },
        "governance": {
            "no_model_deployed": True,
            "production_ready": False,
            "known_limitations": [
                "The benchmark requires at least four closed incidents for a train/test split.",
                "Synthetic evidence is useful for pilot discussion but not operational validation.",
            ],
        },
    }
    report["public_safe_checks"] = public_safe_checks(report)
    return report


def build_ml_baseline_benchmark(
    rows: list[dict[str, Any]] | None = None,
    input_label: str = "data/synthetic/closed_incidents.jsonl",
    test_size: float = 0.25,
    prolonged_threshold_hours: float = 4.0,
) -> dict[str, Any]:
    rows = rows if rows is not None else load_rows(DEFAULT_DATASET)
    if len(rows) < MINIMUM_BENCHMARK_ROWS:
        return _insufficient_rows_report(rows, input_label, prolonged_threshold_hours)

    train_rows, test_rows = _chronological_split(rows, test_size)
    global_mean = _mean_duration(train_rows)
    scada_means = _group_means(train_rows, lambda row: _feature(row, "scada_status"))
    partner_class_means = _group_means(train_rows, lambda row: _feature(row, "partner_class"))

    policy_results = [
        _evaluate_policy(
            name="rules_initial_eta",
            label="Rules-first initial ETA policy",
            model_family="deterministic_policy",
            uses_training_data=False,
            prediction_fn=lambda row: float(row["initial_eta_hours"]),
            test_rows=test_rows,
            prolonged_threshold_hours=prolonged_threshold_hours,
        ),
        _evaluate_policy(
            name="global_mean_duration",
            label="Global mean restoration-duration baseline",
            model_family="statistical_baseline",
            uses_training_data=True,
            prediction_fn=lambda row: global_mean,
            test_rows=test_rows,
            prolonged_threshold_hours=prolonged_threshold_hours,
        ),
        _evaluate_policy(
            name="scada_status_group_mean",
            label="Mean duration grouped by SCADA status",
            model_family="statistical_baseline",
            uses_training_data=True,
            prediction_fn=lambda row: scada_means.get(_feature(row, "scada_status"), global_mean),
            test_rows=test_rows,
            prolonged_threshold_hours=prolonged_threshold_hours,
        ),
        _evaluate_policy(
            name="partner_class_group_mean",
            label="Mean duration grouped by partner class",
            model_family="statistical_baseline",
            uses_training_data=True,
            prediction_fn=lambda row: partner_class_means.get(_feature(row, "partner_class"), global_mean),
            test_rows=test_rows,
            prolonged_threshold_hours=prolonged_threshold_hours,
        ),
    ]
    policies = {policy["name"]: policy for policy in policy_results}
    best_policy = min(policy_results, key=lambda policy: policy["mae_hours"])
    rules_policy = policies["rules_initial_eta"]
    best_prolonged = max(policy_results, key=lambda policy: policy["prolonged_outage"]["recall"])

    report = {
        "report_type": "ml-baseline-benchmark",
        "data_boundary": "synthetic-public-safe",
        "benchmark_ready": True,
        "source_dataset": input_label,
        "dataset": {
            "rows": len(rows),
            "minimum_rows": MINIMUM_BENCHMARK_ROWS,
            "train_rows": len(train_rows),
            "test_rows": len(test_rows),
            "split_strategy": "chronological_holdout",
            "prolonged_threshold_hours": prolonged_threshold_hours,
        },
        "trained_baselines": {
            "global_mean_hours": _round(global_mean),
            "scada_status_group_means": {key: _round(value) for key, value in sorted(scada_means.items())},
            "partner_class_group_means": {
                key: _round(value) for key, value in sorted(partner_class_means.items())
            },
        },
        "policies": policies,
        "benchmark_summary": {
            "primary_metric": "mae_hours",
            "best_policy_by_mae": best_policy["name"],
            "rules_first_policy": "rules_initial_eta",
            "rules_first_mae_hours": rules_policy["mae_hours"],
            "best_policy_mae_hours": best_policy["mae_hours"],
            "mae_delta_vs_rules_hours": _round(best_policy["mae_hours"] - rules_policy["mae_hours"]),
            "interpretation": "Lower MAE on this synthetic holdout is evidence for pilot discussion, not a production model decision.",
        },
        "decision_policy_evidence": {
            "rules_first_underestimation_rate": rules_policy["underestimation_rate"],
            "best_prolonged_recall_policy": best_prolonged["name"],
            "best_prolonged_recall": best_prolonged["prolonged_outage"]["recall"],
            "benchmark_only": True,
            "recommended_next_step": "Run side-by-side shadow evaluation on private sandbox or de-identified pilot data before changing operational policy.",
        },
        "governance": {
            "no_model_deployed": True,
            "production_ready": False,
            "known_limitations": [
                "Small synthetic dataset means metric values are directional only.",
                "Chronological holdout reduces leakage but does not replace pilot validation.",
                "No model is used for live partner recommendations in this public-safe prototype.",
            ],
        },
    }
    report["public_safe_checks"] = public_safe_checks(report)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    dataset = report["dataset"]
    summary = report["benchmark_summary"]
    governance = report["governance"]
    policy_lines = "\n".join(
        (
            f"- {policy['name']}: MAE `{policy['mae_hours']}`, "
            f"underestimation `{policy['underestimation_rate']}`, "
            f"prolonged recall `{policy['prolonged_outage']['recall']}`"
        )
        for policy in report["policies"].values()
    )
    if not policy_lines:
        policy_lines = "- No policy comparison available because the dataset is below the benchmark minimum."
    limitations = "\n".join(f"- {item}" for item in governance["known_limitations"])
    return f"""# ML Baseline Benchmark

Data boundary: `{report['data_boundary']}`
Benchmark ready: `{report['benchmark_ready']}`

## Dataset

- Source: `{report['source_dataset']}`
- Rows: `{dataset['rows']}`
- Train rows: `{dataset['train_rows']}`
- Test rows: `{dataset['test_rows']}`
- Split strategy: `{dataset['split_strategy']}`
- Prolonged-outage threshold hours: `{dataset['prolonged_threshold_hours']}`

## Policy Comparison

{policy_lines}

## Benchmark Summary

- Primary metric: `{summary['primary_metric']}`
- Best policy by MAE: `{summary['best_policy_by_mae']}`
- Rules-first policy: `{summary['rules_first_policy']}`
- Interpretation: {summary['interpretation']}

## Decision Policy Evidence

- Benchmark only: `{report['decision_policy_evidence']['benchmark_only']}`
- Recommended next step: {report['decision_policy_evidence']['recommended_next_step']}

## Governance

- No model deployed: `{governance['no_model_deployed']}`
- Production ready: `{governance['production_ready']}`

{limitations}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a public-safe ML baseline benchmark for ETA policy discussion.")
    parser.add_argument("--input", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--test-size", type=float, default=0.25)
    parser.add_argument("--prolonged-threshold-hours", type=float, default=4.0)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = build_ml_baseline_benchmark(
        rows=load_rows(args.input),
        input_label=_display_path(args.input),
        test_size=args.test_size,
        prolonged_threshold_hours=args.prolonged_threshold_hours,
    )
    rendered = render_markdown(report) if args.format == "markdown" else json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + ("\n" if not rendered.endswith("\n") else ""), encoding="utf-8")
        return
    print(rendered)
    if report["public_safe_checks"]["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

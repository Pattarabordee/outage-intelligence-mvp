# Evaluation

This prototype evaluates the rules-first decision layer before adding heavier ML models. The goal is to make partner-facing ETA decisions measurable, auditable, and safe to improve.

## API And Rule Regression

Run the API and rule regression suite:

```bash
pytest -q
```

Run coverage with the product-readiness gate:

```bash
pytest --cov=apps --cov-report=term-missing --cov-fail-under=80
```

## ETA Baseline

Train a reproducible baseline from synthetic closed incidents:

```bash
python scripts/train_eta_baseline.py
python scripts/evaluate_product_metrics.py
python scripts/run_ml_baseline_benchmark.py
python scripts/public_safe_scan.py
python scripts/run_partner_sandbox_flow.py
python scripts/run_pilot_scenario_matrix.py
python scripts/run_shadow_evaluation_protocol.py
python scripts/generate_readiness_gate.py
python scripts/generate_pilot_report.py
```

The current baseline predicts restoration duration from the mean duration by `scada_status`. It reports:

- `mae_hours`
- `underestimation_rate`
- trained group means

## ML Baseline Benchmark

`scripts/run_ml_baseline_benchmark.py` compares the current rules-first ETA policy against simple statistical baselines on a chronological synthetic holdout:

- rules-first initial ETA
- global mean restoration duration
- mean duration by SCADA status
- mean duration by partner class

The benchmark reports ETA MAE, underestimation rate, overestimation rate, within-one-hour rate, prolonged-outage precision/recall/F1, and partner action distribution. It is intentionally benchmark-only: no model artifact is deployed, production readiness remains false, and the output stays public-safe.

For details, see [ml-baseline-benchmark.md](ml-baseline-benchmark.md).

## Shadow Evaluation Protocol

`scripts/run_shadow_evaluation_protocol.py` validates the pilot data contract, checks synthetic dataset coverage, and runs the baseline benchmark on a larger shadow-evaluation dataset.

```bash
python scripts/run_shadow_evaluation_protocol.py
python scripts/run_shadow_evaluation_protocol.py --format markdown
```

The protocol reports:

- data contract version
- required field coverage
- feature snapshot coverage
- partner class coverage
- SCADA status coverage
- prolonged-outage case count
- benchmark summary
- public-safe status

For the contract, see [pilot-data-contract.md](pilot-data-contract.md). For the protocol, see [shadow-evaluation-protocol.md](shadow-evaluation-protocol.md).

## Product Metrics To Add Next

- ETA error by partner class and SCADA status
- Underestimation rate by prolonged-outage family
- Timeout fallback quality by scenario family
- Decision calibration by confidence band and partner action
- Audit completeness and restoration ground-truth coverage by partner class
- Shadow-vs-live metric drift once governed private pilot data exists

These metrics turn the outage workflow into a data product rather than only a prototype API.

## Private Pilot Evidence Report

`scripts/generate_pilot_report.py` combines workflow evidence, webhook outbox state, pilot success metrics, public-safe controls, and production gaps into a single JSON or Markdown artifact for pilot discussion.

```bash
python scripts/generate_pilot_report.py --format markdown
```

The report includes `sandbox_integration_evidence`, which summarizes whether the local sandbox has exercised incident creation, ETA revision, timeout fallback, restoration closure, duplicate-event handling, and retry behavior.

It also includes `readiness_gate`, which separates private sandbox readiness from production readiness, and `shadow_evaluation_evidence`, which validates the pilot data contract.

## Pilot Scenario Matrix

`scripts/run_pilot_scenario_matrix.py` runs repeatable synthetic scenarios for short outage, prolonged outage, timeout, duplicate event, duplicate signal, retry exhausted, restore idempotency, and partner scope denial.

```bash
python scripts/run_pilot_scenario_matrix.py --format markdown
```

Use this before adding heavier ML so the baseline has stable scenario evidence, not only aggregate metrics.

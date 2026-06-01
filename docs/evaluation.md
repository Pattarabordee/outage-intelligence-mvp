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
python scripts/public_safe_scan.py
python scripts/run_partner_sandbox_flow.py
python scripts/generate_readiness_gate.py
python scripts/generate_pilot_report.py
```

The current baseline predicts restoration duration from the mean duration by `scada_status`. It reports:

- `mae_hours`
- `underestimation_rate`
- trained group means

## Product Metrics To Add Next

- ETA error by partner class
- Timeout fallback rate
- Underestimation rate for prolonged outages
- Decision calibration by confidence band
- Audit completeness and restoration ground-truth coverage
- Prolonged-outage baseline recall

These metrics turn the outage workflow into a data product rather than only a prototype API.

## Private Pilot Evidence Report

`scripts/generate_pilot_report.py` combines workflow evidence, webhook outbox state, pilot success metrics, public-safe controls, and production gaps into a single JSON or Markdown artifact for pilot discussion.

```bash
python scripts/generate_pilot_report.py --format markdown
```

The report includes `sandbox_integration_evidence`, which summarizes whether the local sandbox has exercised incident creation, ETA revision, timeout fallback, restoration closure, duplicate-event handling, and retry behavior.

It also includes `readiness_gate`, which separates private sandbox readiness from production readiness.

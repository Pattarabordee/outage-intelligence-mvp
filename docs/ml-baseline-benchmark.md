# ML Baseline Benchmark

Run this benchmark when the discussion moves from workflow readiness to measurable ETA decision quality.

```bash
python scripts/run_ml_baseline_benchmark.py
python scripts/run_ml_baseline_benchmark.py --format markdown
```

The benchmark uses only synthetic closed incidents. It does not train or deploy a production model, does not call any external service, and does not expose private partner payloads, delivery targets, or operational topology.

## What It Compares

The benchmark evaluates the current rules-first ETA policy against simple statistical baselines:

- `rules_initial_eta`: the deterministic ETA already produced by the rules policy
- `global_mean_duration`: mean restoration duration from the training split
- `scada_status_group_mean`: mean restoration duration grouped by synthetic SCADA status
- `partner_class_group_mean`: mean restoration duration grouped by synthetic partner class

The split is chronological holdout. This keeps the artifact simple, repeatable, and easier to explain in a private sandbox discussion.

## Metrics

The JSON and Markdown outputs include:

- ETA MAE hours
- mean signed error
- underestimation rate
- overestimation rate
- within-one-hour rate
- prolonged-outage precision, recall, and F1
- partner action distribution derived from predicted ETA

These metrics answer operational questions:

- Does the current ETA policy underestimate prolonged outages?
- Which simple baseline sets a measurable floor?
- Does the policy identify cases where backup activation may be needed?
- What evidence would be needed before changing operational policy?

## Governance Boundary

This benchmark is evidence for pilot discussion, not production AI approval.

Current guardrails:

- synthetic data only
- benchmark-only output
- no model artifact deployed
- no outbound network calls
- public-safe output checks
- production readiness remains false

Before a private pilot uses real operational decisions, the benchmark should be rerun on a governed private sandbox dataset with partner-approved data handling, retention rules, and side-by-side shadow evaluation.

## Relationship To Pilot Reports

`scripts/generate_readiness_gate.py` includes the benchmark as `ml_baseline`.

`scripts/generate_pilot_report.py` includes the full artifact as `ml_baseline_evidence`.

Use this after the scenario matrix has passed. The scenario matrix proves repeatable workflow coverage; the ML benchmark proves that ETA policy quality can be measured without adding opaque model behavior.

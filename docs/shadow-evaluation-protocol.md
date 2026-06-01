# Shadow Evaluation Protocol

Run this protocol when the conversation shifts from "the workflow works" to "how would we evaluate ETA quality during a private pilot without affecting operations?"

```bash
python scripts/run_shadow_evaluation_protocol.py
python scripts/run_shadow_evaluation_protocol.py --format markdown
```

The protocol is offline and synthetic. It validates the pilot data contract, runs the ML baseline benchmark, and reports whether the sandbox has enough data shape and governance evidence for a private pilot discussion.

## What The Protocol Proves

- The closed-incident dataset follows `pilot-data-contract-v1`.
- Required top-level and feature snapshot fields are complete.
- Partner classes, SCADA statuses, and prolonged-outage cases are represented.
- The ETA policy can be benchmarked against simple statistical baselines.
- No model is deployed and no operational decision is changed.
- Generated output stays public-safe.

## Evaluation Flow

1. Load `data/synthetic/pilot_data_contract.json`.
2. Load `data/synthetic/shadow_eval_closed_incidents.jsonl`.
3. Validate required fields and allowed values.
4. Check coverage thresholds.
5. Run `scripts/run_ml_baseline_benchmark.py` logic on the same rows.
6. Emit JSON or Markdown evidence for readiness gate and pilot report.

## Acceptance Checks

The protocol currently checks:

- `data_boundary`
- `minimum_rows`
- `required_field_coverage`
- `feature_snapshot_coverage`
- `allowed_partner_class_values`
- `allowed_scada_status_values`
- `minimum_partner_classes`
- `minimum_scada_statuses`
- `minimum_prolonged_cases`
- `baseline_policy_set`
- `shadow_controls`
- `model_governance`
- `public_safe_output`

All checks must pass for `shadow_evaluation_ready` to be `true`.

## How To Read The Result

Use `contract_validation` to discuss data readiness:

- row count
- required field coverage
- feature snapshot coverage
- partner class coverage
- SCADA status coverage
- prolonged-outage case count

Use `benchmark_summary` to discuss decision quality:

- best policy by MAE
- rules-first MAE
- best baseline MAE
- MAE delta against rules-first policy

Use `decision_policy_evidence` to discuss operational risk:

- rules-first underestimation rate
- prolonged-outage recall
- recommended next step before changing policy

## Governance Boundary

This protocol is designed for shadow evaluation only:

- benchmark only
- no deployed model
- no outbound dispatch
- no production decision automation
- no live partner data in the public repo

Before a private pilot uses governed data, the team should define retention, de-identification, partner review, metric ownership, and escalation rules for underestimated prolonged outages.

## Relationship To Other Artifacts

- `scripts/generate_readiness_gate.py` includes the result as `shadow_evaluation`.
- `scripts/generate_pilot_report.py` includes the result as `shadow_evaluation_evidence`.
- `docs/pilot-data-contract.md` defines the contract behind the protocol.
- `docs/ml-baseline-benchmark.md` defines the benchmark comparison used by the protocol.

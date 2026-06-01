# Pilot Success Metrics

This document defines the metrics used to judge whether the private pilot workflow is useful, measurable, and safe to improve. All examples are synthetic and public-safe.

## Primary Decision Metrics

| Metric | Why It Matters | Source |
| --- | --- | --- |
| ETA MAE | Measures average ETA error in hours. | Closed incident dataset |
| Underestimation rate | Flags cases where the ETA was too optimistic. | Closed incident dataset |
| Timeout fallback rate | Shows how often the failsafe path is needed. | Incident audit state |
| Webhook delivery rate | Measures sandbox notification completion. | Local webhook outbox |
| Webhook attempt rate | Shows how often delivery retries or attempts are exercised. | Local webhook outbox |
| Audit completeness | Confirms decisions have traceable events. | Incident event log |
| Ground-truth coverage | Confirms restored cases are usable for evaluation. | Closed incident dataset |
| Partner action distribution | Shows how often the system recommends waiting, preparing, or activating backup. | Operator console summary |
| Sandbox integration coverage | Confirms the local flow exercised create, revise, timeout, restore, duplicate handling, and retry behavior. | Partner sandbox flow |

## Pilot Targets

These are discussion targets, not production SLAs:

- Audit completeness should remain close to `1.0` in synthetic demos.
- Ground-truth coverage should remain close to `1.0` for closed synthetic cases.
- Underestimation rate should trend down before any future supervised-learning model is promoted.
- Timeout fallback rate should be reviewed with operators to separate useful protection from missing evidence.
- Webhook attempt and delivery rates should be used to validate retry-safe partner integration behavior.

## Report Command

Generate the current evidence pack:

```bash
python scripts/generate_pilot_report.py
python scripts/generate_pilot_report.py --format markdown
```

Run the partner sandbox proof before the report when you want integration evidence:

```bash
python scripts/run_partner_sandbox_flow.py
```

The report intentionally excludes private delivery headers, raw field text, production topology, auth material, and partner network targets.

## ML Readiness Gate

Do not move directly to complex ML. The recommended sequence is:

1. Stabilize closed-loop data collection.
2. Measure rule-first ETA performance.
3. Track underestimation and prolonged-outage recall.
4. Add a simple supervised baseline only after the evidence report is stable.
5. Compare any future model against the rules-first baseline before operational use.

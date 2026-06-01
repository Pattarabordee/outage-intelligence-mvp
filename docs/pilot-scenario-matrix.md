# Pilot Scenario Matrix

Run this matrix when the discussion moves from a single sandbox walkthrough to repeatable pilot evidence.

```bash
python scripts/run_pilot_scenario_matrix.py
python scripts/run_pilot_scenario_matrix.py --format markdown
```

The matrix uses only synthetic partners, sites, incidents, and field summaries. It does not send outbound HTTP and does not include private delivery headers, network targets, raw operational payloads, or production topology in generated output.

## Covered Scenarios

The current catalog is stored in `data/synthetic/pilot_scenarios.json`.

It covers:

- short outage restoration closure
- prolonged outage ETA revision
- timeout failsafe
- duplicate event and duplicate signal idempotency
- webhook retry exhausted state
- restore endpoint idempotency
- partner sandbox scope denial

## Output Contract

The JSON output includes:

- `scenario_count`
- `passed`
- `failed`
- `coverage_by_capability`
- `scenario_results`
- `public_safe_checks`

Use `coverage_by_capability` to explain what the sandbox proves. Use `scenario_results` when an operator or partner team asks how a specific case behaved.

## Pilot Benchmark Role

This matrix is a pilot benchmark, not a production certification.

It helps answer:

- Can the API handle partner retries without duplicate incidents?
- Does field evidence revise ETA and partner action?
- Does timeout fallback work for ambiguous cases?
- Can delivery retry behavior be audited locally?
- Does restoration closure create closed-loop evidence?
- Does partner scope control reject out-of-bound synthetic sites?

## Relationship To Readiness Gate

`scripts/generate_readiness_gate.py` uses this matrix as readiness evidence. The gate should remain:

- `sandbox_pilot_ready`: `true`
- `production_ready`: `false`

If any scenario fails, the readiness gate should move to remediation before the repo is used for a private sandbox discussion.

## ML Readiness

The matrix prepares the next ML phase by making evaluation cases repeatable. It does not train a new model. Future supervised-learning work should compare any ETA model against this scenario benchmark and the existing rules-first baseline.

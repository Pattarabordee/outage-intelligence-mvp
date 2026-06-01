# Private Pilot Runbook

This runbook supports a public-safe private pilot discussion for the enterprise outage intelligence prototype. It is not a production operating manual.

## 1. Pre-Demo Setup

Use a clean local environment and synthetic data only.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/seed_demo_data.py
uvicorn apps.api.main:app --reload
```

Open these routes:

- Executive walkthrough: `http://127.0.0.1:8000/demo/incidents`
- Operator console: `http://127.0.0.1:8000/demo/operator-console`
- API docs: `http://127.0.0.1:8000/docs`

## 2. Executive Walkthrough

Use `/demo/incidents` first. The goal is to explain product value before showing operator detail.

Recommended talk track:

1. An enterprise outage event arrives through the partner-facing API.
2. The system returns an immediate ETA and partner action.
3. Field evidence revises the ETA and confidence band.
4. Timeout fallback prevents stalled cases.
5. Restoration closure creates ground truth for evaluation and future ML.

## 3. Operator Console Walkthrough

Use `/demo/operator-console` after the executive story.

Recommended sequence:

1. Start with `Highest Attention` to show what the operator should inspect first.
2. Review `Current Operating Status` for active incidents, timeout risk, webhook queue, and closed-loop rows.
3. Use `Active Incidents` to discuss priority labels and next-step guidance.
4. Use `Timeout Risk` to explain failsafe behavior and SLA-style decision protection.
5. Use `Webhook Queue` to discuss partner notification readiness without sending network traffic.
6. Use `Pilot Report Snapshot` to connect the console to evaluation metrics.
7. Use `Public-Safe Controls` to reinforce that no operationally sensitive details are rendered.

## 4. Partner Sandbox Integration Flow

Run the repeatable local sandbox proof:

```bash
python scripts/run_partner_sandbox_flow.py
```

Use the JSON output to discuss:

- duplicate event handling
- duplicate field signal handling
- local retry and delivery attempt behavior
- restoration idempotency
- timeout fallback coverage
- whether the scenario is ready for pilot reporting

For the full walkthrough, see [partner-sandbox-playbook.md](partner-sandbox-playbook.md).

## 5. Pilot Scenario Matrix

Run the scenario benchmark:

```bash
python scripts/run_pilot_scenario_matrix.py
python scripts/run_pilot_scenario_matrix.py --format markdown
```

Use [pilot-scenario-matrix.md](pilot-scenario-matrix.md) to review short outage, prolonged outage, timeout, duplicate, retry exhausted, restore idempotency, and partner scope cases.

## 6. Readiness Gate

Run the private sandbox readiness gate:

```bash
python scripts/public_safe_scan.py
python scripts/run_ml_baseline_benchmark.py
python scripts/run_shadow_evaluation_protocol.py
python scripts/generate_readiness_gate.py
```

Use [private-sandbox-acceptance-criteria.md](private-sandbox-acceptance-criteria.md) as the go/no-go checklist. The expected discussion outcome is `ready_for_private_sandbox_discussion`, not production approval.

## 7. ML Baseline Benchmark

Run the ETA policy benchmark:

```bash
python scripts/run_ml_baseline_benchmark.py
python scripts/run_ml_baseline_benchmark.py --format markdown
```

Use [ml-baseline-benchmark.md](ml-baseline-benchmark.md) to compare the rules-first ETA policy with simple statistical baselines. The discussion should focus on measurable pilot evidence, underestimation risk, prolonged-outage recall, and why no model is deployed from this public-safe prototype.

## 8. Pilot Data Contract And Shadow Evaluation

Run the shadow protocol:

```bash
python scripts/run_shadow_evaluation_protocol.py
python scripts/run_shadow_evaluation_protocol.py --format markdown
```

Use [pilot-data-contract.md](pilot-data-contract.md) to review the dataset shape and [shadow-evaluation-protocol.md](shadow-evaluation-protocol.md) to explain how ETA policy quality can be measured without affecting partner-facing operations.

## 9. Webhook Retry Discussion

The prototype records local outbox events instead of sending HTTP callbacks. This keeps the public repo safe while demonstrating retry and deduplication design.

Discuss:

- partner-scoped delivery records
- retry scheduling
- delivery attempt history
- future receiver-side verification for a private sandbox
- why no live network target is stored in the repository

## 10. Evaluation And ML-Readiness Discussion

Generate a pilot evidence report:

```bash
python scripts/generate_pilot_report.py
python scripts/generate_pilot_report.py --format markdown
```

Use the report to connect product behavior to measurable pilot outcomes:

- ETA error
- underestimation risk
- timeout fallback rate
- webhook delivery and attempt rates
- audit completeness
- restoration ground-truth coverage
- partner action distribution
- sandbox integration evidence
- readiness gate decision
- scenario matrix evidence
- ML baseline evidence
- shadow evaluation evidence

## 11. Production Gaps Before Live Use

The prototype is ready for pilot discussion, not live production use.

Before a real private pilot, close these gaps:

- production-grade authentication and partner authorization
- managed database and migration plan
- outbound delivery worker and receiver-side verification
- live telemetry, alerting, and incident-owner runbooks
- data retention, de-identification, and governance review

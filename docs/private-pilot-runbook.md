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

## 4. Webhook Retry Discussion

The prototype records local outbox events instead of sending HTTP callbacks. This keeps the public repo safe while demonstrating retry and deduplication design.

Discuss:

- partner-scoped delivery records
- retry scheduling
- delivery attempt history
- future receiver-side verification for a private sandbox
- why no live network target is stored in the repository

## 5. Evaluation And ML-Readiness Discussion

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

## 6. Production Gaps Before Live Use

The prototype is ready for pilot discussion, not live production use.

Before a real private pilot, close these gaps:

- production-grade authentication and partner authorization
- managed database and migration plan
- outbound delivery worker and receiver-side verification
- live telemetry, alerting, and incident-owner runbooks
- data retention, de-identification, and governance review

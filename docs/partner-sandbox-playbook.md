# Partner Sandbox Integration Playbook

This playbook turns the public-safe prototype into a repeatable sandbox integration proof. It is designed for utility operations, enterprise account teams, and partner NOC teams that want to review workflow behavior before a private pilot.

The flow stays local. It records delivery intent and retry attempts in SQLite; it does not send outbound HTTP or store partner network targets.

## 1. Setup

Start from a clean checkout with synthetic data only:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Optional demo seed:

```bash
python scripts/seed_demo_data.py
```

## 2. Run The Sandbox Flow

Run the isolated scenario:

```bash
python scripts/run_partner_sandbox_flow.py
```

The command uses a temporary local database by default. Use `--db-path` only when you intentionally want to write the scenario into a named local SQLite file.

Expected JSON sections:

- `scenario`: confirms the execution model and synthetic data boundary
- `incident_id`: the synthetic incident used for the primary flow
- `idempotency_result`: proves duplicate event and signal submissions do not create duplicate state
- `webhook_retry_result`: proves local retry and delivery attempt behavior without network dispatch
- `restore_result`: proves restoration closure is idempotent
- `timeout_result`: proves timeout fallback can be exercised in the same sandbox run
- `report_ready`: confirms the flow produced enough closed-loop evidence for pilot reporting
- `public_safe_checks`: confirms the summary excludes private headers, raw payloads, and network targets

## 3. Review The Flow With A Partner Team

Use the JSON output to walk through the partner operating story:

1. A synthetic partner profile scopes the sandbox site IDs.
2. A synthetic outage event creates an incident and immediate ETA decision.
3. A repeated event returns the same incident, proving retry-safe ingestion.
4. A field signal revises ETA and creates a delivery record.
5. A failed delivery attempt is recorded locally, then a delivered attempt closes the retry loop.
6. Restoration closes the incident and creates ML-ready ground truth.
7. A timeout case demonstrates failsafe behavior for ambiguous evidence.

## 4. Generate Evidence Report

Generate the pilot report after a seed run or a sandbox flow written to a named local database:

```bash
python scripts/public_safe_scan.py
python scripts/generate_readiness_gate.py
python scripts/generate_pilot_report.py
python scripts/generate_pilot_report.py --format markdown
```

The report now includes `sandbox_integration_evidence`, which summarizes:

- local outbox mode
- flow coverage
- retry behavior
- idempotency controls
- closed-loop report readiness
- private pilot gaps before live use

The report also includes `readiness_gate`, which summarizes whether the sandbox is ready for private pilot discussion while keeping production readiness explicitly false.

## 5. Discussion Boundary

This sandbox proves workflow shape, retry-safety, auditability, and reporting readiness. It does not prove production authorization, managed delivery workers, replay-window enforcement, live telemetry, or regulatory governance for operational data.

Keep the conversation scoped to pilot readiness:

- Are partner events idempotent?
- Are ETA decisions explainable?
- Can the NOC see what needs attention?
- Are delivery retries auditable?
- Is restoration ground truth captured for evaluation?
- Which production gaps must close before live operation?

# Pilot Data Contract

This contract defines the synthetic closed-incident rows used for private sandbox shadow evaluation. It turns the ML-readiness discussion into an explicit data product contract instead of a loose dataset note.

Machine-readable contract: `data/synthetic/pilot_data_contract.json`

Synthetic evaluation dataset: `data/synthetic/shadow_eval_closed_incidents.jsonl`

## Capability

The platform can export closed outage incidents in a stable, public-safe shape so a utility team and an enterprise partner team can evaluate ETA quality, underestimation risk, timeout behavior, and prolonged-outage detection before any operational policy change.

## Constraints

- All rows are synthetic and public-safe.
- The contract covers evaluation data only, not live partner ingestion.
- No row may include private delivery headers, operator notes, live network targets, customer identifiers, or production topology.
- The dataset is suitable for shadow evaluation and pilot discussion, not production model approval.
- Future private pilot data must go through partner-approved data handling, retention, and de-identification rules.

## Required Row Fields

| Field | Type | Purpose |
| --- | --- | --- |
| `incident_id` | string | Synthetic closed incident identifier. |
| `prediction_time` | ISO-8601 string | Time when the ETA decision was made. |
| `actual_restoration_duration_hours` | number | Ground-truth restoration duration. |
| `initial_eta_hours` | number | Rules-first ETA at incident creation. |
| `eta_error_hours` | number | `initial_eta_hours - actual_restoration_duration_hours`. |
| `rule_version` | string | Decision policy version used for the ETA. |
| `audit_event_count` | integer | Number of audit events attached to the incident. |
| `feature_snapshot` | object | Public-safe features available at prediction time. |

## Required Feature Snapshot Fields

| Field | Type | Purpose |
| --- | --- | --- |
| `partner_id` | string | Synthetic partner scope identifier. |
| `partner_class` | enum | Example partner category such as telecom, data center, or hospital network. |
| `scada_status` | enum | Synthetic initial utility status. |
| `province` | string | Generalized zone label, not a real operating location. |
| `source_event_id_present` | boolean | Whether the inbound event had an idempotency reference. |
| `timeout_applied` | boolean | Whether timeout fallback was part of the incident lifecycle. |

## Accepted Values

Partner classes:

- `telecom`
- `industrial_estate`
- `hospital_network`
- `data_center`
- `critical_infrastructure`

SCADA statuses:

- `OUTAGE_CONFIRMED`
- `UNKNOWN`
- `POWER_NORMAL`

## Acceptance Thresholds

The current public-safe shadow dataset must satisfy:

- at least 20 rows
- at least 4 partner classes
- at least 3 SCADA statuses
- at least 4 prolonged-outage cases using a 4-hour threshold
- required field coverage of `1.0`
- feature snapshot coverage of `1.0`

These are pilot evidence thresholds, not production SLAs.

## Interfaces

Run contract validation and shadow evaluation:

```bash
python scripts/run_shadow_evaluation_protocol.py
python scripts/run_shadow_evaluation_protocol.py --format markdown
```

The JSON output includes:

- `contract_validation`
- `acceptance_checks`
- `benchmark_summary`
- `decision_policy_evidence`
- `shadow_protocol`
- `public_safe_checks`

## Non-Goals

- No live integration is performed.
- No model artifact is deployed.
- No automatic partner-facing policy change is made.
- No external service is called.
- No production readiness is claimed.

## Open Questions For A Private Pilot

- Which partner classes and outage categories should be included in the governed pilot dataset?
- What retention period applies to restored incident ground truth?
- Which team approves de-identification and export boundaries?
- What underestimation threshold is acceptable before operator review is required?
- Which metric is the primary pilot gate: ETA MAE, underestimation rate, or prolonged-outage recall?

## Handoff

Use this contract before any private sandbox data exchange. The next engineering step is to run the shadow evaluation protocol on a governed private sandbox extract and compare it with the public-safe synthetic benchmark.

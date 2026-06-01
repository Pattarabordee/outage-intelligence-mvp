# Partner Integration Guide

This guide describes how an enterprise partner system could integrate with the outage intelligence API using synthetic, public-safe examples.

## Target Operators

- Utility operations team: owns outage state and restoration updates.
- Enterprise account team: coordinates communication with strategic partners.
- Partner NOC/SOC: consumes ETA and decides whether to activate backup operations.
- Partner operations team: executes backup power, field escalation, or site-level contingency actions.

## Integration Flow

1. Partner system sends an outage event with `source_event_id`.
2. API creates an incident and returns ETA, recommendation, partner action, confidence, and policy explanation.
3. Utility field signals revise the ETA through `/signals/field`.
4. Timeout check applies a deterministic fallback if evidence is missing.
5. Restoration closes the incident and preserves ground truth for analytics.

## Synthetic Partner Payload

```json
{
  "client_name": "DemoEnterprisePartner",
  "partner_id": "partner-telecom-sandbox",
  "site_id": "SITE-1001",
  "province": "North Zone",
  "scada_status": "OUTAGE_CONFIRMED",
  "source_event_id": "SRC-EVENT-1001"
}
```

## Idempotency Policy

- `source_event_id` or `idempotency_key` prevents duplicate incident creation.
- `source_signal_id` prevents duplicate signal ingestion.
- Timeout checks and restore operations are safe to retry.
- `source_event_id` is unique within a partner boundary.

## Sandbox Authentication

For local public demos, sandbox auth is disabled unless `OUTAGE_SANDBOX_API_KEYS` is configured.

When enabled, clients must send:

- `X-Partner-Id`
- `X-API-Key`

The request `partner_id`, when present, must match `X-Partner-Id`.

## Data Minimization

Send only the operational fields needed for outage decisions. Avoid real names, chat messages, endpoint URLs, topology, GPS coordinates, and commercial terms in public prototype environments.

## Example Partner Classes

The same flow can support large-scale telecom operators, data centers, industrial estates, hospital networks, transport operators, or other critical infrastructure partners without changing the core outage decision model.

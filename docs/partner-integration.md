# Partner Integration Guide

This guide describes how an enterprise partner system could integrate with the outage intelligence API using synthetic, public-safe examples.

## Target Operators

- Utility operations team: owns outage state and restoration updates.
- Enterprise account team: coordinates communication with strategic partners.
- Partner NOC/SOC: consumes ETA and decides whether to activate backup operations.
- Partner operations team: executes backup power, field escalation, or site-level contingency actions.

## Integration Flow

1. Partner sandbox profile defines partner class, synthetic site scope, and webhook mode.
2. Partner system sends an outage event with `source_event_id`.
3. API creates an incident and returns ETA, recommendation, partner action, confidence, and policy explanation.
4. Utility field signals revise the ETA through `/signals/field`.
5. Timeout check applies a deterministic fallback if evidence is missing.
6. Webhook delivery records and sandbox attempts track partner notification readiness.
7. Restoration closes the incident and preserves ground truth for analytics.

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
- Webhook notifications use `event_id` as the partner-side deduplication key.

## Sandbox Authentication

For local public demos, sandbox auth is disabled unless `OUTAGE_SANDBOX_API_KEYS` is configured.

When enabled, clients must send:

- `X-Partner-Id`
- `X-API-Key`

The request `partner_id`, when present, must match `X-Partner-Id`.

## Partner Sandbox Profile

Use `PUT /api/v1/partners/{partner_id}/sandbox-profile` to configure public-safe pilot metadata:

- `partner_class`: example partner category such as `telecom`, `data_center`, or `hospital_network`
- `allowed_site_prefixes`: synthetic site prefixes the partner is allowed to submit
- `webhook_mode`: `outbox_only` or `mock_dispatch`
- `notification_contact_label`: a generic label for demo storytelling, not a real endpoint

The profile boundary is intentionally lightweight. It demonstrates pilot readiness without claiming production-grade master data, authorization, or topology management.

## Webhook Outbox

This public prototype uses a local outbox instead of sending real callbacks:

- `GET /api/v1/webhook-deliveries` lists partner-scoped delivery records.
- `GET /api/v1/webhook-deliveries/{event_id}` retrieves one delivery record.
- `POST /api/v1/webhook-deliveries/{event_id}/retry` schedules a local retry and updates attempt metadata.
- `POST /api/v1/webhook-deliveries/{event_id}/attempts` records a sandbox delivery outcome such as `delivered` or `failed`.
- `GET /api/v1/webhook-deliveries/{event_id}/attempts` lists sandbox delivery attempts.

Configure `OUTAGE_WEBHOOK_SECRET` to generate sandbox HMAC signatures in `X-Webhook-Signature`. Do not store real callback URLs, production secrets, or partner endpoint details in this repository.

## Executive Walkthrough

Use `python scripts/seed_demo_data.py` and open `/demo/incidents` to walk through the product story with an enterprise partner. The page is designed for a short pilot conversation:

- outage incident opened
- initial ETA and partner action returned
- field evidence revises ETA
- webhook delivery attempt is tracked
- restoration creates ML-ready ground truth

The JSON feed at `/api/v1/demo/executive-summary` is sanitized for public demos and excludes private delivery headers and raw field transcripts.

## Data Minimization

Send only the operational fields needed for outage decisions. Avoid real names, chat messages, endpoint URLs, topology, GPS coordinates, and commercial terms in public prototype environments.

## Example Partner Classes

The same flow can support large-scale telecom operators, data centers, industrial estates, hospital networks, transport operators, or other critical infrastructure partners without changing the core outage decision model.

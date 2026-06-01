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

## Operator Pilot Console

Use `/demo/operator-console` after seeding demo data to review the same product concept from a utility or partner NOC perspective.

The operator console is intentionally different from the executive walkthrough:

- executive walkthrough explains product value in a short partner conversation
- operator console answers what needs attention now during a private pilot workflow
- active incidents show ETA, confidence band, reason code, and update age
- timeout risk highlights incidents approaching or using fallback policy
- webhook queue shows sandbox delivery records that need retry or awareness
- closed-loop data shows whether restoration outcomes are ready for evaluation

The JSON feed at `/api/v1/operator/console-summary` is read-only and sanitized. It does not expose private delivery headers, raw field text, signing metadata, or callback details.

## 3-Minute Private Pilot Walkthrough

Use this sequence when presenting the sandbox to utility operations, enterprise account, or partner NOC stakeholders:

1. Open `/demo/incidents` and explain the value path: event received, ETA returned, field signal revises ETA, timeout protects stalled cases, restoration creates ground truth.
2. Switch to `/demo/operator-console` and start with the highest attention banner.
3. Review active incidents using `operator_priority` and `operator_next_step` instead of scanning every raw record.
4. Show timeout risk and webhook queue as the two operational queues that need attention before partner handoff.
5. Close with closed-loop data coverage and explain which production gaps remain before live use.

## Data Minimization

Send only the operational fields needed for outage decisions. Avoid real names, chat messages, endpoint URLs, topology, GPS coordinates, and commercial terms in public prototype environments.

## Example Partner Classes

The same flow can support large-scale telecom operators, data centers, industrial estates, hospital networks, transport operators, or other critical infrastructure partners without changing the core outage decision model.

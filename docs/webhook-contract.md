# Webhook Contract

This document describes the public-safe outbound notification contract for a future partner pilot. The current prototype records webhook delivery intent in a local outbox; it does not send HTTP callbacks.

## Delivery Model

- Partner systems register a sandbox callback URL in a private environment, not in this public repo.
- Each notification carries an event type, event id, partner id, incident id, and decision summary.
- Delivery should be retry-safe through `event_id` idempotency.
- Delivery records can be inspected through `/api/v1/webhook-deliveries`.
- Sandbox retry scheduling is available through `/api/v1/webhook-deliveries/{event_id}/retry`.
- Sandbox delivery outcomes can be recorded through `/api/v1/webhook-deliveries/{event_id}/attempts`.
- Production pilots should sign payloads with an environment-managed webhook secret.
- No outbound HTTP request is made by this public prototype.

## Event Types

- `incident.created`
- `eta.revised`
- `timeout.applied`
- `incident.restored`
- `duplicate.ignored`

## Example Payload

```json
{
  "event_id": "evt-synthetic-001",
  "event_type": "eta.revised",
  "partner_id": "partner-telecom-sandbox",
  "incident_id": "INC-EXAMPLE",
  "occurred_at": "2026-06-01T10:00:00+00:00",
  "decision": {
    "eta_hours": 7.0,
    "recommendation": "DISPATCH_BACKUP_IF_BATTERY_WINDOW_AT_RISK",
    "partner_action": "Activate backup operations if the site battery window is at risk.",
    "confidence_band": "high",
    "reason_code": "STRUCTURAL_DAMAGE",
    "policy_version": "rules-v1"
  }
}
```

## Signature Policy For A Private Pilot

Recommended headers:

- `X-Partner-Id`
- `X-Webhook-Event-Id`
- `X-Webhook-Signature`
- `X-Webhook-Timestamp`

Signature verification should use an HMAC secret stored in environment configuration. Do not commit webhook secrets, real callback URLs, or partner-specific endpoints.

In this prototype:

- Set `OUTAGE_WEBHOOK_SECRET` to produce `sha256=<digest>` signatures.
- Leave `OUTAGE_WEBHOOK_SECRET` unset to mark payloads as `unsigned`.
- Set `OUTAGE_WEBHOOK_MAX_ATTEMPTS` to control local retry scheduling, default `3`.

## Retry And Idempotency

- Partners should store processed `event_id` values.
- Retries must not duplicate partner-side ticket updates.
- Out-of-order delivery should be handled by comparing `occurred_at` and current incident status.
- The local retry endpoint updates outbox state only; production delivery workers would be implemented in a private deployment.

## Sandbox Attempt States

The public prototype supports a mock dispatcher state machine:

- `queued`: delivery intent has been recorded.
- `retry_scheduled`: a failed attempt or manual retry has scheduled another local attempt.
- `delivered`: sandbox receiver simulation accepted the event.
- `exhausted`: max local attempts were reached.

Attempt records store only synthetic status metadata such as outcome, response status, and public-safe error text.

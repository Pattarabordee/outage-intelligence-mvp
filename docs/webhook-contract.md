# Webhook Contract

This document describes the public-safe outbound notification contract for a future partner pilot. The current prototype documents payloads only; it does not send HTTP callbacks.

## Delivery Model

- Partner systems register a sandbox callback URL in a private environment, not in this public repo.
- Each notification carries an event type, event id, partner id, incident id, and decision summary.
- Delivery should be retry-safe through `event_id` idempotency.
- Production pilots should sign payloads with an environment-managed webhook secret.

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

## Retry And Idempotency

- Partners should store processed `event_id` values.
- Retries must not duplicate partner-side ticket updates.
- Out-of-order delivery should be handled by comparing `occurred_at` and current incident status.

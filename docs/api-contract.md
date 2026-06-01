# Partner API Contract

This contract describes a public-safe partner-facing API shape for enterprise outage coordination. All examples use synthetic identifiers and synthetic payloads.

## POST `/api/v1/incidents`

Creates an outage incident and returns an immediate ETA decision for partner operations.

Request:

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

Response:

```json
{
  "incident": {
    "id": "INC-EXAMPLE",
    "partner_id": "partner-telecom-sandbox",
    "status": "HOLD_SENT",
    "current_eta_hours": 2.0,
    "reason_code": "SCADA_INITIAL_ASSESSMENT"
  },
  "recommendation": "HOLD_BACKUP_DISPATCH",
  "decision": {
    "eta_hours": 2.0,
    "recommendation": "HOLD_BACKUP_DISPATCH",
    "partner_action": "Wait for the next utility update before activating backup operations.",
    "confidence_band": "medium",
    "reason_code": "SCADA_INITIAL_ASSESSMENT",
    "policy_version": "rules-v1",
    "policy_explanation": "The current evidence indicates a short restoration window, so partner backup dispatch can remain on hold.",
    "sla_behavior": {
      "timeout_minutes": 120,
      "timeout_fallback_eta_hours": 8.0,
      "idempotency_fields": ["source_event_id", "idempotency_key", "source_signal_id"]
    }
  }
}
```

Notes:

- New incidents return `201 Created` with a `Location` header.
- Repeated `source_event_id` or `idempotency_key` returns the existing incident with `200 OK`.
- The decision object is intended for NOC/SOC, enterprise account, or partner operations teams.
- If sandbox keys are configured, requests must include `X-Partner-Id` and `X-API-Key`.
- `partner_id` is the tenant boundary. If provided in the body, it must match the authenticated `X-Partner-Id`.

## POST `/api/v1/incidents/{incident_id}/signals/field`

Processes a synthetic field text signal and revises ETA if needed.

Request:

```json
{
  "channel": "FIELD_APP",
  "raw_text": "Field crew reports tree on line near segment B",
  "observed_at": "2026-06-01T10:00:00+00:00",
  "source_signal_id": "SRC-SIGNAL-1001"
}
```

Response includes:

- current incident state
- all persisted field signals
- all incident audit events
- current decision object with partner action and policy explanation

Repeated `source_signal_id` returns the existing signal result without duplicating audit records.

## POST `/api/v1/incidents/{incident_id}/timeout-check`

Applies a worst-case ETA if the incident exceeds the timeout threshold.

SLA-style behavior:

- timeout window: `120` minutes
- fallback ETA: `8.0` hours
- operation is idempotent
- repeated calls do not create duplicate timeout events

## POST `/api/v1/incidents/{incident_id}/restore`

Closes the incident and logs the restoration timestamp for future analytics or ML training.

## GET `/api/v1/webhook-deliveries`

Lists local webhook outbox records for the authenticated partner. This prototype does not send outbound HTTP callbacks; it records delivery intent, signed metadata, payload, status, and retry state for sandbox integration review.

Example response:

```json
[
  {
    "event_id": "evt-synthetic-001",
    "partner_id": "partner-telecom-sandbox",
    "incident_id": "INC-EXAMPLE",
    "event_type": "eta.revised",
    "payload": {
      "event_id": "evt-synthetic-001",
      "event_type": "eta.revised",
      "partner_id": "partner-telecom-sandbox",
      "incident_id": "INC-EXAMPLE"
    },
    "headers": {
      "X-Partner-Id": "partner-telecom-sandbox",
      "X-Webhook-Event-Id": "evt-synthetic-001",
      "X-Webhook-Signature": "sha256=synthetic-example",
      "X-Webhook-Timestamp": "2026-06-01T10:00:00+00:00"
    },
    "status": "queued",
    "attempt_count": 0,
    "max_attempts": 3,
    "next_attempt_at": null,
    "last_error": null,
    "created_at": "2026-06-01T10:00:00+00:00",
    "updated_at": "2026-06-01T10:00:00+00:00"
  }
]
```

## POST `/api/v1/webhook-deliveries/{event_id}/retry`

Schedules a local retry for a queued delivery record. The endpoint increments `attempt_count`, sets `status` to `retry_scheduled`, and calculates `next_attempt_at` using a simple backoff policy. It does not send network traffic.

Access is partner-scoped: one partner cannot inspect or retry another partner's delivery record.

## Error Format

All API errors use the same shape:

```json
{
  "error": {
    "code": "not_found",
    "message": "Incident not found: INC-EXAMPLE",
    "details": []
  }
}
```

Common error codes:

- `unauthorized`
- `forbidden`
- `invalid_signature`
- `duplicate_event`
- `not_found`
- `state_conflict`
- `validation_error`

## Public-Safe Boundary

This contract is a reference shape for product discussion. It excludes authentication secrets, real partner endpoints, production topology, real field messages, and customer-specific identifiers.

# API Contract

## POST `/api/v1/incidents`
Creates an outage incident and returns an immediate ETA recommendation.

Request:
```json
{
  "client_name": "DemoOperator",
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
    "status": "HOLD_SENT",
    "current_eta_hours": 2.0,
    "reason_code": "SCADA_INITIAL_ASSESSMENT"
  },
  "recommendation": "HOLD_BACKUP_DISPATCH",
  "decision": {
    "eta_hours": 2.0,
    "recommendation": "HOLD_BACKUP_DISPATCH",
    "confidence_band": "medium",
    "reason_code": "SCADA_INITIAL_ASSESSMENT",
    "policy_version": "rules-v1"
  }
}
```

Notes:
- New incidents return `201 Created` with a `Location` header.
- Repeated `source_event_id` or `idempotency_key` returns the existing incident with `200 OK`.

## POST `/api/v1/incidents/{incident_id}/signals/field`
Processes a field text signal and revises ETA if needed.

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
- the current incident state
- all persisted field signals
- all incident audit events
- the current decision object

## POST `/api/v1/incidents/{incident_id}/timeout-check`
Applies a worst-case ETA if the incident exceeds the timeout threshold.

The timeout operation is idempotent. Repeated calls do not create duplicate timeout events.

## POST `/api/v1/incidents/{incident_id}/restore`
Closes the incident and logs the restoration timestamp for future analytics or ML training.

## Error format

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
- `not_found`
- `state_conflict`
- `validation_error`

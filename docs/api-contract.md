# API Contract

## POST `/api/v1/incidents`
Creates an outage incident and returns an immediate ETA recommendation.

Request:
```json
{
  "client_name": "DemoOperator",
  "site_id": "SITE-1001",
  "province": "North Zone",
  "scada_status": "OUTAGE_CONFIRMED"
}
```

## POST `/api/v1/incidents/{incident_id}/signals/field`
Processes a field text signal and revises ETA if needed.

Request:
```json
{
  "channel": "FIELD_APP",
  "raw_text": "Field crew reports tree on line near segment B"
}
```

## POST `/api/v1/incidents/{incident_id}/timeout-check`
Applies a worst-case ETA if the incident exceeds the timeout threshold.

## POST `/api/v1/incidents/{incident_id}/restore`
Closes the incident and logs the restoration timestamp for future analytics or ML training.

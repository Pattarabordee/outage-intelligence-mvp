from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from typing import Any


def json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(json_safe(payload), sort_keys=True, separators=(",", ":"))


def sign_payload(payload_json: str, secret: str | None) -> str:
    if not secret:
        return "unsigned"
    digest = hmac.new(secret.encode("utf-8"), payload_json.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def build_webhook_headers(
    payload_json: str,
    partner_id: str,
    event_id: str,
    occurred_at: str,
    secret: str | None,
) -> dict[str, str]:
    return {
        "X-Partner-Id": partner_id,
        "X-Webhook-Event-Id": event_id,
        "X-Webhook-Timestamp": occurred_at,
        "X-Webhook-Signature": sign_payload(payload_json, secret),
    }

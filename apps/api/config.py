from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


def parse_sandbox_api_keys(value: str | None = None) -> dict[str, str]:
    raw_value = value if value is not None else os.getenv("OUTAGE_SANDBOX_API_KEYS", "")
    keys: dict[str, str] = {}
    for item in raw_value.split(","):
        if not item.strip() or ":" not in item:
            continue
        partner_id, api_key = item.split(":", 1)
        if partner_id.strip() and api_key.strip():
            keys[partner_id.strip()] = api_key.strip()
    return keys


@dataclass(frozen=True)
class Settings:
    api_title: str = "Enterprise Outage Intelligence API"
    api_version: str = "0.2.0"
    policy_version: str = "rules-v1"
    db_path: Path = Path(os.getenv("OUTAGE_DB_PATH", Path(tempfile.gettempdir()) / "outage_intelligence_demo.db"))
    sandbox_api_keys: dict[str, str] = field(default_factory=parse_sandbox_api_keys)


settings = Settings()

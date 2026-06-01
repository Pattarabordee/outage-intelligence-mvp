from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("enterprise_outage_intelligence")


def log_event(event_type: str, **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "event_type": event_type,
        **fields,
    }
    logger.info(json.dumps(payload, sort_keys=True, default=str))

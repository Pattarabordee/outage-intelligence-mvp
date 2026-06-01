from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    api_title: str = "Enterprise Outage Intelligence API"
    api_version: str = "0.2.0"
    policy_version: str = "rules-v1"
    db_path: Path = Path(os.getenv("OUTAGE_DB_PATH", Path(tempfile.gettempdir()) / "outage_intelligence_demo.db"))


settings = Settings()

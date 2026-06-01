from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.main import create_app


@pytest.fixture
def client():
    tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db_path = os.path.join(tmpdir.name, "test.db")
    test_client = TestClient(create_app(db_path=db_path))
    try:
        yield test_client
    finally:
        test_client.close()
        tmpdir.cleanup()

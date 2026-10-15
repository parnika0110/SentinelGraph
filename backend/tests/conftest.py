"""Shared fixtures.

All tests run against the LIVE FalkorDB container (the same database the
demo uses). The demo dataset is loaded once per session; ingestion is
idempotent, so this is safe to re-run.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import pytest

# Demo alert ids (deterministic dataset, data/demo_alerts.json)
ALERT_A = "ALR-2026-10-0011"  # suspicious login (seed)
ALERT_B = "ALR-2026-10-0012"  # payments-server C2 beacon  -> must group
ALERT_C = "ALR-2026-10-0013"  # marketing laptop malware    -> must NOT group
ALERT_HIST = "ALR-2026-04-0091"  # archived alert (historical=true)
HIST_INCIDENT_1 = "INC-2025-0417"
HIST_INCIDENT_2 = "INC-2025-0512"


@pytest.fixture(scope="session", autouse=True)
def seeded_dataset() -> dict:
    from app.graph.schema import ensure_schema
    from app.ingestion.loader import load_demo_dataset_from_path
    from app.config import get_settings

    settings = get_settings()
    ensure_schema(settings)
    data_path = BACKEND_DIR.parent / "data" / "demo_alerts.json"
    return load_demo_dataset_from_path(str(data_path))


@pytest.fixture(scope="session")
def client(seeded_dataset):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c

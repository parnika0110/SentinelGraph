"""SentinelGraph API -- FastAPI application entry point.

Run from backend/:
    uvicorn app.main:app --reload --port 8000

Startup: ensures FalkorDB schema/indexes and auto-seeds the synthetic demo
dataset when the graph is empty (configurable via AUTO_SEED_ON_STARTUP).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.graph.connection import run_query
from app.graph.schema import ensure_schema, schema_document
from app.ingestion.loader import load_demo_dataset_from_path
from app.routes import ALL_ROUTERS

API_VERSION = "1.0.0"

API_DESCRIPTION = """
SentinelGraph is a graph-powered cybersecurity incident investigation agent
built on FalkorDB. The graph is the reasoning and memory layer: every fact
returned by the API comes from parameterized Cypher retrieval.

**Core endpoints**
- `GET  /health` -- service + database status
- `POST /alerts` / `POST /alerts/ingest` -- idempotent alert ingestion
- `POST /investigations` -- run a graph investigation for an alert
- `GET  /investigations/{id}` -- retrieve a persisted investigation
- `GET  /graph/neighborhood/{id}` -- bounded subgraph for the explorer
- `POST /memories` -- store findings / analyst feedback
- `POST /actions`, `/actions/{id}/approve`, `/actions/{id}/reject` --
  simulated, approval-gated response actions
- `GET  /incidents`, `/incidents/{id}` -- incident queue and detail
- `POST /demo/reset` -- reseed the synthetic demo dataset

All actions are simulated. All data is synthetic.
"""


def _seed_if_empty() -> dict:
    settings = get_settings()
    ensure_schema(settings)
    if not settings.auto_seed_on_startup:
        return {"seeded": False, "reason": "auto_seed disabled"}
    count = run_query("MATCH (a:Alert) RETURN count(a)")[0][0]
    if count:
        return {"seeded": False, "reason": f"{count} alerts already present"}
    data_path = __import__("pathlib").Path(__file__).resolve().parents[2] / "data" / "demo_alerts.json"
    counts = load_demo_dataset_from_path(str(data_path))
    return {"seeded": True, "counts": counts}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = _seed_if_empty()
    app.state.seed_state = state
    yield


app = FastAPI(
    title="SentinelGraph API",
    description=API_DESCRIPTION,
    version=API_VERSION,
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in ALL_ROUTERS:
    app.include_router(router)


@app.get("/", tags=["system"])
def root() -> dict:
    """API index: documents every available endpoint."""
    return {
        "name": "SentinelGraph API",
        "version": API_VERSION,
        "docs": "/docs",
        "endpoints": [
            {"method": "GET", "path": "/health"},
            {"method": "GET", "path": "/"},
            {"method": "POST", "path": "/alerts"},
            {"method": "POST", "path": "/alerts/ingest"},
            {"method": "GET", "path": "/alerts"},
            {"method": "GET", "path": "/alerts/{id}"},
            {"method": "POST", "path": "/investigations"},
            {"method": "GET", "path": "/investigations"},
            {"method": "GET", "path": "/investigations/{id}"},
            {"method": "GET", "path": "/graph/neighborhood/{id}"},
            {"method": "GET", "path": "/graph/schema"},
            {"method": "POST", "path": "/memories"},
            {"method": "GET", "path": "/memories"},
            {"method": "POST", "path": "/actions"},
            {"method": "POST", "path": "/actions/{id}/approve"},
            {"method": "POST", "path": "/actions/{id}/reject"},
            {"method": "POST", "path": "/actions/{id}/complete"},
            {"method": "GET", "path": "/actions?incident_id="},
            {"method": "GET", "path": "/incidents"},
            {"method": "GET", "path": "/incidents/{id}"},
            {"method": "POST", "path": "/demo/reset"},
        ],
        "schema": schema_document()["node_labels"],
        "all_data_synthetic": True,
        "actions_simulated": True,
    }

"""Demo maintenance endpoint (reseed the synthetic dataset)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from app.config import get_settings
from app.graph.connection import drop_graph, run_query
from app.graph.schema import ensure_schema
from app.ingestion.loader import load_demo_dataset_from_path

router = APIRouter(prefix="/demo", tags=["demo"])

DATA_PATH = Path(__file__).resolve().parents[3] / "data" / "demo_alerts.json"


@router.post("/reset")
def reset_demo_dataset() -> dict:
    """Drop + reseed the synthetic dataset (idempotent, demo convenience)."""
    settings = get_settings()
    drop_graph(settings.graph_name, settings)
    ensure_schema(settings)
    counts = load_demo_dataset_from_path(str(DATA_PATH))
    alerts = run_query("MATCH (a:Alert) RETURN count(a)")[0][0]
    return {"status": "reseeded", "counts": counts, "alerts_in_graph": alerts}

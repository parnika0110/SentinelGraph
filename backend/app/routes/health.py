"""GET /health -- liveness + FalkorDB reachability + graph counts."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.graph.connection import run_query
from app.models import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    try:
        run_query("RETURN 1", settings=settings)
        status, db_status = "ok", "connected"
    except Exception as exc:  # pragma: no cover
        return HealthResponse(
            status="degraded",
            falkordb=f"error: {type(exc).__name__}",
            graph=settings.graph_name,
            counts={},
        )

    counts: dict[str, int] = {}
    for label in ["Alert", "Incident", "Evidence", "Memory", "Action", "Investigation"]:
        try:
            counts[label.lower()] = run_query(
                f"MATCH (n:{label}) RETURN count(n)", settings=settings
            )[0][0]
        except Exception:  # pragma: no cover
            counts[label.lower()] = -1
    return HealthResponse(status=status, falkordb=db_status, graph=settings.graph_name, counts=counts)

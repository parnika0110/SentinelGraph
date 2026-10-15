"""Investigation endpoints.

POST /investigations          -- run a graph investigation for an alert
GET  /investigations          -- list past investigation runs
GET  /investigations/{id}     -- reconstruct a persisted investigation
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.graph.connection import run_query
from app.investigation.engine import get_investigation, run_investigation
from app.models import InvestigationRequest, InvestigationResult

router = APIRouter(tags=["investigations"])


@router.post("/investigations", response_model=InvestigationResult, status_code=201)
def create_investigation(req: InvestigationRequest) -> InvestigationResult:
    """Execute the investigation pipeline against FalkorDB."""
    try:
        return run_investigation(req.alert_id, req.analyst)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc


@router.get("/investigations/{investigation_id}", response_model=InvestigationResult)
def fetch_investigation(investigation_id: str) -> InvestigationResult:
    """Rebuild a stored investigation from graph artifacts (proves persistence)."""
    result = get_investigation(investigation_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"Investigation {investigation_id} not found"
        )
    return result


@router.get("/investigations")
def list_investigations() -> dict:
    rows = run_query(
        "MATCH (i:Investigation) RETURN properties(i) ORDER BY i.created_at DESC LIMIT 100"
    )
    items = []
    for (props,) in rows:
        items.append(
            {
                "id": props.get("id"),
                "seed_alert_id": props.get("seed_alert_id"),
                "created_at": props.get("created_at"),
                "analyst": props.get("analyst"),
                "incident_id": props.get("incident_id") or None,
                "related_alert_ids": props.get("related_alert_ids", []),
            }
        )
    return {"count": len(items), "investigations": items}

"""Incident queue + detail endpoints.

GET /incidents        -- queue (severity/status filters)
GET /incidents/{id}   -- incident detail: alerts, evidence, actions, memories,
                         similarity links
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.action_workflow import list_actions
from app.config import get_settings
from app.graph.connection import run_query
from app.graph.queries import INCIDENT_ACTIONS, INCIDENT_ALERTS, INCIDENT_EVIDENCE, INCIDENT_MEMORIES
from app.memory import fetch_historical_context
from app.models import ActionOut

router = APIRouter(tags=["incidents"])


@router.get("/incidents")
def list_incidents(
    severity: str | None = Query(None, pattern="^(low|medium|high|critical)$"),
    status: str | None = Query(None, pattern="^(OPEN|CLOSED)$"),
) -> dict:
    where = ["true"]
    params: dict = {}
    if severity:
        where.append("i.severity = $severity")
        params["severity"] = severity
    if status:
        where.append("i.status = $status")
        params["status"] = status
    cypher = f"""
MATCH (i:Incident)
WHERE {' AND '.join(where)}
OPTIONAL MATCH (a:Alert)-[:PART_OF]->(i)
OPTIONAL MATCH (act:Action)-[:PROPOSED_FOR]->(i)
RETURN i, collect(DISTINCT a.id), collect(DISTINCT act.status)
ORDER BY i.opened_at DESC
"""
    rows = run_query(cypher, params)
    incidents = []
    for node, alert_ids, action_statuses in rows:
        props = dict(node.properties)
        statuses = [s for s in action_statuses if s]
        incidents.append(
            {
                "id": props.get("id"),
                "title": props.get("title"),
                "summary": props.get("summary", ""),
                "severity": props.get("severity"),
                "status": props.get("status"),
                "opened_at": props.get("opened_at"),
                "alert_ids": alert_ids,
                "alert_count": len(alert_ids),
                "action_counts": {
                    "PROPOSED": statuses.count("PROPOSED"),
                    "APPROVED": statuses.count("APPROVED"),
                    "REJECTED": statuses.count("REJECTED"),
                    "COMPLETED": statuses.count("COMPLETED"),
                },
            }
        )
    return {"count": len(incidents), "incidents": incidents}


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> dict:
    rows = run_query(
        "MATCH (i:Incident {id: $id}) RETURN properties(i)", {"id": incident_id}
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    props = rows[0][0]

    alerts = [
        {"id": r[0], **r[1]} for r in run_query(INCIDENT_ALERTS, {"incident_id": incident_id})
    ]
    evidence = [
        {"id": r[0], **{k: v for k, v in r[1].items() if k != "path_json"}}
        for r in run_query(INCIDENT_EVIDENCE, {"incident_id": incident_id})
    ]
    actions = [
        a.model_dump() for a in list_actions(incident_id)
    ]
    memories = [
        {"id": r[0], **r[1]} for r in run_query(INCIDENT_MEMORIES, {"incident_id": incident_id})
    ]
    investigations = run_query(
        "MATCH (i:Investigation {incident_id: $id}) RETURN i.id, i.created_at, i.seed_alert_id",
        {"id": incident_id},
    )
    historical = fetch_historical_context(
        incident_id, get_settings().memory_similarity_threshold
    )

    return {
        "id": incident_id,
        "props": props,
        "alerts": alerts,
        "evidence": evidence,
        "actions": actions,
        "memories": memories,
        "investigations": [
            {"id": r[0], "created_at": r[1], "seed_alert_id": r[2]} for r in investigations
        ],
        "historical_context": historical,
    }

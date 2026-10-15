"""Alert endpoints: single + bulk ingestion (idempotent) and the alert queue.

POST /alerts         -- ingest one validated alert (upsert, idempotent)
POST /alerts/ingest  -- bulk ingest (upsert, idempotent)
GET  /alerts         -- alert queue with severity/investigated filters
GET  /alerts/{id}    -- one alert with its linked entities (provenance)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.graph.connection import run_query
from app.graph.queries import ALERT_ENTITIES, GET_ALERT
from app.ingestion.loader import ingest_alert, ingest_alerts
from app.models import AlertAck, AlertIn, BulkAlertAck, BulkAlertIn

router = APIRouter(tags=["alerts"])


@router.post("/alerts", response_model=AlertAck, status_code=201)
def create_alert(alert: AlertIn) -> AlertAck:
    """Ingest a single alert. Re-POSTing the same alert_id is a no-op upsert."""
    return ingest_alert(alert)


@router.post("/alerts/ingest", response_model=BulkAlertAck, status_code=201)
def bulk_ingest(payload: BulkAlertIn) -> BulkAlertAck:
    """Bulk ingestion endpoint (idempotent upserts on stable ids)."""
    accepted, created, updated, entity_ids = ingest_alerts(payload.alerts)
    return BulkAlertAck(accepted=accepted, created=created, updated=updated, entity_ids=entity_ids)


@router.get("/alerts")
def list_alerts(
    severity: str | None = Query(None, pattern="^(low|medium|high|critical)$"),
    include_historical: bool = False,
    ungrouped_only: bool = False,
) -> dict:
    """Incident queue source: live alerts with optional filters."""
    where = ["NOT coalesce(a.historical, false)"] if not include_historical else ["true"]
    if severity:
        where.append("a.severity = $severity")
    if ungrouped_only:
        where.append("NOT (a)-[:PART_OF]->()")
    cypher = f"""
MATCH (a:Alert)
WHERE {' AND '.join(where)}
OPTIONAL MATCH (a)-[:PART_OF]->(i:Incident)
RETURN a, i.id
ORDER BY a.ts DESC
LIMIT 500
"""
    rows = run_query(cypher, {"severity": severity} if severity else {})
    alerts = []
    for node, incident_id in rows:
        props = dict(node.properties)
        alerts.append(
            {
                "id": props.get("id"),
                "title": props.get("title"),
                "severity": props.get("severity"),
                "alert_type": props.get("alert_type"),
                "ts": props.get("ts"),
                "source": props.get("source"),
                "incident_id": incident_id,
                "status": "grouped" if incident_id else "new",
                "tags": props.get("tags", []),
            }
        )
    return {"count": len(alerts), "alerts": alerts}


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: str) -> dict:
    """One alert plus its linked entities with edge provenance."""
    rows = run_query(GET_ALERT, {"alert_id": alert_id})
    if not rows:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    props = dict(rows[0][0].properties)
    entities = [
        {
            "label": r[0],
            "id": r[1],
            "rel": r[3],
            "rel_props": r[4],
            "props": r[2],
        }
        for r in run_query(ALERT_ENTITIES, {"alert_id": alert_id})
    ]
    incident = run_query(
        "MATCH (a:Alert {id: $id})-[:PART_OF]->(i:Incident) RETURN i.id",
        {"id": alert_id},
    )
    return {
        "id": props.get("id"),
        "props": props,
        "entities": entities,
        "incident_id": incident[0][0] if incident else None,
    }

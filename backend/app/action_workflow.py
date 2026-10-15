"""Simulated action workflow with analyst approval gating.

Statuses: PROPOSED -> APPROVED -> COMPLETED, or PROPOSED -> REJECTED.
Every action in SentinelGraph is SIMULATED: approving never touches a real
system. The approval step is mandatory -- there is no code path that creates
an action already APPROVED, and transitions are validated against the current
status stored in FalkorDB.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.graph.connection import run_query
from app.ingestion.loader import upsert_node, upsert_rel
from app.models import (
    ActionCreate,
    ActionOut,
    ActionStatus,
    ActionType,
    DecisionIn,
    normalize_ts,
)

# Relationship/graph queries for actions.
_Q_GET = """
MATCH (a:Action {id: $id})-[p:PROPOSED_FOR]->(inc:Incident)
OPTIONAL MATCH (a)-[d:APPROVED_BY]->(an:Analyst)
RETURN a.id, properties(a), inc.id, an.id, d.decision, d.reason, d.decided_at
"""

_Q_LIST = """
MATCH (a:Action)-[:PROPOSED_FOR]->(inc:Incident {id: $incident_id})
OPTIONAL MATCH (a)-[d:APPROVED_BY]->(an:Analyst)
RETURN a.id, properties(a), inc.id, an.id, d.decision, d.reason, d.decided_at
ORDER BY a.created_at ASC
"""

_Q_INCIDENT_EXISTS = "MATCH (i:Incident {id: $id}) RETURN i.id"

_VALID_TRANSITIONS: dict[ActionStatus, set[ActionStatus]] = {
    ActionStatus.PROPOSED: {ActionStatus.APPROVED, ActionStatus.REJECTED},
    ActionStatus.APPROVED: {ActionStatus.COMPLETED},
    ActionStatus.REJECTED: set(),
    ActionStatus.COMPLETED: set(),
}


class ActionError(ValueError):
    """Invalid workflow transition or missing entity (mapped to HTTP 409/404)."""

    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


def _now() -> str:
    return normalize_ts(datetime.now(timezone.utc))


def _row_to_action(row) -> ActionOut:
    aid, props, incident_id, analyst_id, decision, reason, decided_at = row
    evidence_ids = props.get("evidence_ids") or []
    if isinstance(evidence_ids, str):
        evidence_ids = []
    return ActionOut(
        id=aid,
        incident_id=incident_id,
        action_type=props.get("action_type", ActionType.INVESTIGATE_ACCOUNT.value),
        target_id=props.get("target_id", ""),
        description=props.get("description", ""),
        status=ActionStatus(props.get("status", ActionStatus.PROPOSED.value)),
        evidence_ids=list(evidence_ids),
        created_by=props.get("created_by", "unknown"),
        created_at=props.get("created_at", ""),
        decided_at=decided_at or props.get("decided_at"),
        decided_by=analyst_id.replace("analyst:", "") if analyst_id else None,
        decision_reason=reason,
        simulated=True,
    )


def get_action(action_id: str) -> ActionOut | None:
    rows = run_query(_Q_GET, {"id": action_id})
    return _row_to_action(rows[0]) if rows else None


def list_actions(incident_id: str) -> list[ActionOut]:
    rows = run_query(_Q_LIST, {"incident_id": incident_id})
    return [_row_to_action(r) for r in rows]


def create_action(payload: ActionCreate) -> ActionOut:
    """Create a PROPOSED action. Approval is a separate, explicit step."""
    exists = run_query(_Q_INCIDENT_EXISTS, {"id": payload.incident_id})
    if not exists:
        raise ActionError(f"Incident {payload.incident_id} not found", status_code=404)

    import uuid

    action_id = f"act:{uuid.uuid4().hex[:12]}"
    created_at = _now()
    props = {
        "action_type": payload.action_type.value,
        "target_id": payload.target_id,
        "description": payload.description,
        "status": ActionStatus.PROPOSED.value,
        "evidence_ids": payload.evidence_ids,
        "created_by": payload.created_by,
        "created_at": created_at,
        "simulated": True,
    }
    upsert_node("Action", action_id, props)
    upsert_rel(action_id, "PROPOSED_FOR", payload.incident_id, {"proposed_at": created_at})

    analyst_id = f"analyst:{payload.created_by.lstrip('@')}"
    upsert_node("Analyst", analyst_id, {"handle": payload.created_by})
    # Ensure the creating analyst is linked to the incident for auditability.
    upsert_rel(analyst_id, "INVESTIGATED", payload.incident_id, {"started_at": created_at})

    created = get_action(action_id)
    assert created is not None
    return created


def _transition(action_id: str, target: ActionStatus, decision: DecisionIn) -> ActionOut:
    current = get_action(action_id)
    if current is None:
        raise ActionError(f"Action {action_id} not found", status_code=404)
    if target not in _VALID_TRANSITIONS[current.status]:
        raise ActionError(
            f"Invalid transition {current.status.value} -> {target.value}: "
            f"only {sorted(s.value for s in _VALID_TRANSITIONS[current.status]) or 'nothing'} allowed",
            status_code=409,
        )

    decided_at = _now()
    run_query(
        "MATCH (a:Action {id: $id}) SET a.status = $status, a.decided_at = $decided_at",
        {"id": action_id, "status": target.value, "decided_at": decided_at},
    )
    analyst_id = f"analyst:{decision.analyst.lstrip('@')}"
    upsert_node("Analyst", analyst_id, {"handle": decision.analyst})
    upsert_rel(
        action_id,
        "APPROVED_BY",
        analyst_id,
        {
            "decision": target.value,
            "reason": decision.reason,
            "decided_at": decided_at,
        },
    )
    updated = get_action(action_id)
    assert updated is not None
    return updated


def approve_action(action_id: str, decision: DecisionIn) -> ActionOut:
    """PROPOSED -> APPROVED. Requires an explicit analyst decision."""
    return _transition(action_id, ActionStatus.APPROVED, decision)


def reject_action(action_id: str, decision: DecisionIn) -> ActionOut:
    """PROPOSED -> REJECTED."""
    return _transition(action_id, ActionStatus.REJECTED, decision)


def complete_action(action_id: str, decision: DecisionIn) -> ActionOut:
    """APPROVED -> COMPLETED (marks the simulated action as executed)."""
    return _transition(action_id, ActionStatus.COMPLETED, decision)


def suggested_actions_for(
    incident_id: str,
    seed_alert_id: str,
    account_ids: list[str],
    device_ids: list[str],
    external_ip_ids: list[str],
    evidence_ids: list[str],
    created_by: str,
) -> list[ActionOut]:
    """Create deterministic, evidence-backed PROPOSED actions.

    Only ever proposes; the analyst must approve each one separately.
    """
    existing = list_actions(incident_id)
    existing_keys = {(a.action_type, a.target_id) for a in existing}

    candidates: list[tuple[ActionType, str, str]] = []
    if account_ids:
        candidates.append(
            (
                ActionType.INVESTIGATE_ACCOUNT,
                account_ids[0],
                f"Review recent activity and session history for {account_ids[0]} "
                f"(linked to {seed_alert_id}). Simulated investigation task.",
            )
        )
        candidates.append(
            (
                ActionType.DISABLE_ACCOUNT,
                account_ids[0],
                f"Disable {account_ids[0]} pending analyst confirmation (SIMULATED - "
                "no real identity system is contacted).",
            )
        )
    for dev in device_ids[:2]:
        candidates.append(
            (
                ActionType.REVIEW_DEVICE,
                dev,
                f"Collect forensic triage package from {dev} (SIMULATED collection task).",
            )
        )
    if len(device_ids) >= 2:
        candidates.append(
            (
                ActionType.ISOLATE_DEVICE,
                device_ids[0],
                f"Isolate {device_ids[0]} from the network (SIMULATED - no real "
                "EDR or network control is contacted). Chosen because retrieved "
                "paths show lateral movement from this host.",
            )
        )
    for ip in external_ip_ids[:2]:
        candidates.append(
            (
                ActionType.BLOCK_IP,
                ip,
                f"Add {ip} to the egress blocklist (SIMULATED - no real firewall "
                "is contacted).",
            )
        )

    created: list[ActionOut] = []
    for action_type, target, description in candidates:
        if (action_type, target) in existing_keys:
            continue
        try:
            created.append(
                create_action(
                    ActionCreate(
                        incident_id=incident_id,
                        action_type=action_type,
                        target_id=target,
                        description=description,
                        evidence_ids=evidence_ids,
                        created_by=created_by,
                    )
                )
            )
        except ActionError:
            continue
    # Idempotent: return the full set for the incident (created or existing),
    # so repeat investigations still surface the pending proposals.
    return created + [a for a in list_actions(incident_id) if a.id not in {c.id for c in created}]

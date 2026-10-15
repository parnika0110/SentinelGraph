"""Action workflow endpoints (all actions are SIMULATED).

POST /actions                 -- create a PROPOSED action for an incident
POST /actions/{id}/approve    -- PROPOSED -> APPROVED (explicit analyst step)
POST /actions/{id}/reject     -- PROPOSED -> REJECTED
POST /actions/{id}/complete   -- APPROVED -> COMPLETED (simulated execution)
GET  /actions                 -- list actions for an incident
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.action_workflow import (
    ActionError,
    approve_action,
    complete_action,
    create_action,
    get_action,
    list_actions,
    reject_action,
)
from app.models import ActionCreate, ActionOut, DecisionIn

router = APIRouter(tags=["actions"])


def _handle(exc: ActionError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/actions", response_model=ActionOut, status_code=201)
def create(payload: ActionCreate) -> ActionOut:
    """Propose a simulated action. It starts in PROPOSED and cannot skip review."""
    try:
        return create_action(payload)
    except ActionError as exc:
        raise _handle(exc) from exc


@router.post("/actions/{action_id}/approve", response_model=ActionOut)
def approve(action_id: str, decision: DecisionIn) -> ActionOut:
    """PROPOSED -> APPROVED with an explicit analyst decision record."""
    try:
        return approve_action(action_id, decision)
    except ActionError as exc:
        raise _handle(exc) from exc


@router.post("/actions/{action_id}/reject", response_model=ActionOut)
def reject(action_id: str, decision: DecisionIn) -> ActionOut:
    """PROPOSED -> REJECTED with an explicit analyst decision record."""
    try:
        return reject_action(action_id, decision)
    except ActionError as exc:
        raise _handle(exc) from exc


@router.post("/actions/{action_id}/complete", response_model=ActionOut)
def complete(action_id: str, decision: DecisionIn) -> ActionOut:
    """APPROVED -> COMPLETED (marks the simulated action as executed)."""
    try:
        return complete_action(action_id, decision)
    except ActionError as exc:
        raise _handle(exc) from exc


@router.get("/actions")
def list_for_incident(incident_id: str = Query(...)) -> dict:
    items = list_actions(incident_id)
    return {"count": len(items), "actions": [a.model_dump() for a in items]}


@router.get("/actions/{action_id}", response_model=ActionOut)
def fetch(action_id: str) -> ActionOut:
    action = get_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail=f"Action {action_id} not found")
    return action

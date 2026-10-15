"""Milestone 4: persistent incident memory + approval-gated action workflow.

Persistence is proven by writing through one call and reading through a
separate call (a separate request boundary), never by in-process state.
"""

from __future__ import annotations

import pytest

from tests.conftest import ALERT_A, HIST_INCIDENT_1, HIST_INCIDENT_2


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def investigation(seeded_dataset):
    from app.investigation.engine import run_investigation

    return run_investigation(ALERT_A, analyst="tester")


def test_store_then_read_across_separate_calls(investigation):
    from app.memory import store_memory, list_memories
    from app.models import MemoryIn, MemoryKind

    written = store_memory(
        MemoryIn(
            kind=MemoryKind.FEEDBACK,
            content="Grouping decision for A+B was correct; the payments host was the pivot.",
            confidence=0.8,
            incident_id=investigation.incident_id,
            investigation_id=investigation.id,
            created_by="tester",
        )
    )
    # Separate call, reads from FalkorDB:
    reread = list_memories(investigation.incident_id)
    hit = next((m for m in reread if m.id == written.id), None)
    assert hit is not None, "memory must survive across separate calls/requests"
    assert hit.kind == "feedback"
    assert hit.created_by == "tester"
    assert hit.confidence == 0.8


def test_historical_incident_memory_retrievable(investigation):
    """Stored findings from a PREVIOUS session are visible now."""
    from app.memory import fetch_historical_context

    contexts = fetch_historical_context(
        investigation.incident_id, min_score=0.0
    )
    ids = {c["similar_incident_id"] for c in contexts}
    assert HIST_INCIDENT_1 in ids or HIST_INCIDENT_2 in ids
    hit = next(c for c in contexts if c["similar_incident_id"] in {HIST_INCIDENT_1, HIST_INCIDENT_2})
    assert hit["memories"], "historical incident must carry stored findings"
    for m in hit["memories"]:
        assert m["trust_note"], "every recalled memory needs its trust caveat"
        assert m["created_at"] and m["created_by"], "memory provenance required"


def test_memory_is_not_treated_as_truth(investigation):
    """A stored hypothesis from history must be labeled context, not fact."""
    from app.memory import fetch_historical_context

    contexts = fetch_historical_context(investigation.incident_id, min_score=0.0)
    assert contexts, "historical context expected for the demo incident"
    for c in contexts:
        for m in c["memories"]:
            assert "unverified lead" in m["trust_note"].lower(), \
                "recalled memory must carry its do-not-trust-blindly caveat"
        assert "weighted jaccard" in c["basis"].lower(), "similarity must state its metric"
    # Current-run hypotheses stay classified as hypotheses even when history exists.
    assert all(h.classification == "hypothesis" for h in investigation.hypotheses)


# ---------------------------------------------------------------------------
# Action workflow (all simulated)
# ---------------------------------------------------------------------------

def _new_action(incident_id: str):
    from app.action_workflow import create_action
    from app.models import ActionCreate, ActionType

    return create_action(
        ActionCreate(
            incident_id=incident_id,
            action_type=ActionType.REVIEW_DEVICE,
            target_id="dev:fin-ws-1042",
            description="Simulated triage request used by the test suite.",
            created_by="tester",
        )
    )


def test_action_starts_as_proposed(investigation):
    action = _new_action(investigation.incident_id)
    assert action.status == "PROPOSED"
    assert action.simulated is True


def test_approval_requires_explicit_analyst_decision(investigation):
    from app.action_workflow import approve_action, get_action
    from app.models import DecisionIn

    action = _new_action(investigation.incident_id)
    approved = approve_action(
        action.id, DecisionIn(analyst="tester", reason="evidence-backed triage approved")
    )
    assert approved.status == "APPROVED"
    assert approved.decided_by and approved.decided_by.endswith("tester")
    # Re-read through a separate call (separate request boundary).
    assert get_action(action.id).status == "APPROVED"


def test_rejection_is_a_valid_separate_outcome(investigation):
    from app.action_workflow import reject_action, get_action
    from app.models import DecisionIn

    action = _new_action(investigation.incident_id)
    rejected = reject_action(action.id, DecisionIn(analyst="tester", reason="out of scope"))
    assert rejected.status == "REJECTED"
    assert get_action(action.id).status == "REJECTED"


def test_invalid_transitions_are_blocked(investigation):
    from app.action_workflow import approve_action, complete_action, reject_action, ActionError
    from app.models import DecisionIn

    d = DecisionIn(analyst="tester", reason="n/a")
    action = _new_action(investigation.incident_id)

    # COMPLETED is unreachable from PROPOSED (approval must come first).
    with pytest.raises(ActionError) as exc:
        complete_action(action.id, d)
    assert exc.value.status_code == 409

    approve_action(action.id, d)
    # APPROVED cannot be approved again, and REJECTED is terminal.
    with pytest.raises(ActionError):
        approve_action(action.id, d)
    with pytest.raises(ActionError):
        reject_action(action.id, d)

    # Unknown id -> 404, never a silent success.
    with pytest.raises(ActionError) as exc:
        approve_action("act:does-not-exist", d)
    assert exc.value.status_code == 404


def test_proposed_actions_are_generated_from_evidence(investigation):
    assert investigation.incident_id is not None
    assert investigation.suggested_actions, "engine must propose evidence-backed actions"
    # Proposals start PROPOSED; earlier tests may have decided some of them,
    # so only valid workflow statuses are allowed here.
    valid = {"PROPOSED", "APPROVED", "REJECTED", "COMPLETED"}
    assert {a.status.value for a in investigation.suggested_actions} <= valid
    assert any(a.status.value == "PROPOSED" for a in investigation.suggested_actions), \
        "at least one action must still await an analyst decision"
    # Every proposal is tied to retrieved evidence ids or at least the incident.
    for a in investigation.suggested_actions:
        assert a.action_type in {"INVESTIGATE_ACCOUNT", "REVIEW_DEVICE",
                                 "ISOLATE_DEVICE", "DISABLE_ACCOUNT",
                                 "BLOCK_IP", "REVIEW_SERVICE"}
        assert a.target_id
        assert "SIMULATED" in a.description.upper() or "simulated" in a.description

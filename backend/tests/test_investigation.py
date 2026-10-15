"""Milestone 3: graph-driven investigation engine.

Covers the three required cases:
  1. connected alerts   -> grouped with a REAL retrieved graph path
  2. unrelated alerts   -> NOT grouped, with a transparent exclusion reason
  3. missing evidence   -> explicit gaps, never invented away
plus provenance and persistence across separate calls.
"""

from __future__ import annotations

import pytest

from tests.conftest import ALERT_A, ALERT_B, ALERT_C, ALERT_HIST, HIST_INCIDENT_1

ALLOWED_TELEMETRY_RELS = {
    "INVOLVES", "OBSERVED_ON", "REFERENCES_IP", "LOGGED_IN_FROM", "USED",
    "RUNS", "CONNECTS_TO", "DEPENDS_ON", "PART_OF",
}


@pytest.fixture(scope="module")
def result(seeded_dataset):
    from app.investigation.engine import run_investigation

    return run_investigation(ALERT_A, analyst="tester")


# --------------------------------------------------------------------------
# 1. Connected case
# --------------------------------------------------------------------------

def test_b_is_grouped_with_a(result):
    assert ALERT_B in result.related_alert_ids


def test_evidence_path_is_a_real_retrieved_path(result):
    """The A->B evidence must be an actual path with real nodes + edges."""
    path_ab = next(
        (e.path for e in result.evidence
         if e.path and e.path.nodes[0].id == ALERT_A and e.path.nodes[-1].id == ALERT_B),
        None,
    )
    assert path_ab is not None, "no A->B evidence path retrieved from FalkorDB"
    assert len(path_ab.nodes) >= 3, "must be a genuine multi-hop path"
    assert len(path_ab.edges) == len(path_ab.nodes) - 1
    for edge in path_ab.edges:
        assert edge.type in ALLOWED_TELEMETRY_RELS
    # Chain consistency: each edge connects consecutive nodes in the chain.
    for i, edge in enumerate(path_ab.edges):
        pair = {edge.src, edge.dst}
        assert pair == {path_ab.nodes[i].id, path_ab.nodes[i + 1].id}


def test_path_edges_carry_timestamps_and_provenance(result):
    path_ab = next(
        e.path for e in result.evidence
        if e.path and e.path.nodes[-1].id == ALERT_B
    )
    assert any(edge.props.get("ts") for edge in path_ab.edges), \
        "retrieved relationships must keep timestamps"
    ev = next(e for e in result.evidence if e.path is path_ab)
    assert {ALERT_A, ALERT_B} <= set(ev.source_alert_ids)


def test_facts_and_hypotheses_are_separated(result):
    assert result.observed_facts, "observed facts must be present"
    assert result.hypotheses, "hypotheses must be present"
    assert all(h.classification == "hypothesis" for h in result.hypotheses)
    # Every hypothesis cites evidence that actually exists in this result.
    ev_ids = {e.id for e in result.evidence}
    for h in result.hypotheses:
        assert set(h.supporting_evidence_ids) <= ev_ids
        assert h.rationale, "hypothesis must expose its score rationale"


def test_hypothesis_confidence_derives_from_score(result):
    h = next(h for h in result.hypotheses if ALERT_B in h.statement)
    assert 0.0 <= h.confidence <= 1.0
    assert h.confidence >= 0.5  # a grouped link scores above the floor


# --------------------------------------------------------------------------
# 2. Unrelated case
# --------------------------------------------------------------------------

def test_unrelated_alert_c_is_not_grouped(result):
    assert ALERT_C not in result.related_alert_ids


def test_c_exclusion_reason_explains_external_ip(result):
    exc = next(e for e in result.excluded_alert_ids if e["alert_id"] == ALERT_C)
    reason = exc["reason"].lower()
    assert "external" in reason or "public ip" in reason
    assert exc["breakdown"]["entity_score"] <= 0, \
        "sharing an external IP must contribute zero entity score"


def test_historical_alert_is_context_not_grouping(result):
    assert ALERT_HIST not in result.related_alert_ids
    exc = next(e for e in result.excluded_alert_ids if e["alert_id"] == ALERT_HIST)
    assert "historical" in exc["reason"].lower()


def test_seed_alert_with_no_internal_links_groups_nothing(seeded_dataset):
    """Investigating the unrelated alert C must not sweep A/B into it."""
    from app.investigation.engine import run_investigation

    res = run_investigation(ALERT_C, analyst="tester")
    assert ALERT_A not in res.related_alert_ids
    assert ALERT_B not in res.related_alert_ids
    # And the engine must say so explicitly rather than staying silent.
    assert res.hypotheses, "a no-grouping result still needs a stated hypothesis"


# --------------------------------------------------------------------------
# 3. Missing evidence
# --------------------------------------------------------------------------

def test_missing_evidence_is_reported_not_hidden(result):
    assert result.missing_evidence, "engine must surface telemetry gaps"
    assert any("process" in gap.lower() for gap in result.missing_evidence)


def test_missing_evidence_attached_to_hypotheses(result):
    for h in result.hypotheses:
        assert h.missing_evidence == result.missing_evidence


# --------------------------------------------------------------------------
# Persistence (separate calls = separate "requests")
# --------------------------------------------------------------------------

def test_investigation_survives_a_separate_request(result):
    from app.investigation.engine import get_investigation

    back = get_investigation(result.id)
    assert back is not None
    assert back.seed_alert_id == result.seed_alert_id
    assert back.related_alert_ids == result.related_alert_ids
    assert len(back.evidence) == len(result.evidence)
    assert back.incident_id == result.incident_id
    assert [h.id for h in back.hypotheses] == [h.id for h in result.hypotheses]


def test_historical_memory_is_retrieved_with_provenance(result):
    assert result.historical_context, "historical incidents must be retrieved"
    hit = next(
        (h for h in result.historical_context if h.similar_incident_id == HIST_INCIDENT_1),
        None,
    )
    assert hit is not None, f"{HIST_INCIDENT_1} should be linked as similar history"
    assert hit.score > 0
    # Similarity must be explained by shared graph entities, not vibes.
    assert "shared entities" in hit.basis
    # Trust policy: retrieved memory is context, not confirmed truth.
    if hit.memories:
        assert all("unverified lead" in m.get("trust_note", "") for m in hit.memories)


def test_memory_finding_written_for_incident(result):
    from app.memory import list_memories

    memories = list_memories(result.incident_id)
    findings = [m for m in memories if m.kind == "finding"]
    assert findings, "investigation must persist a finding into incident memory"
    assert any(result.seed_alert_id in m.content for m in findings)

"""Persistent incident memory (stored in FalkorDB, survives sessions).

Memory nodes hold investigation findings and analyst feedback with provenance
(created_by, created_at, investigation_id, confidence). Retrieval goes through
graph relationships: SIMILAR_TO between incidents -> PART_OF -> Memory.

Trust policy: retrieved memories are *historical context*, never confirmed
truth. Every returned memory carries its provenance and a caveat that it must
be re-validated against current evidence; hypotheses stored earlier are not
promoted to facts just because they live in memory.
"""

from __future__ import annotations

import datetime

from app.graph.connection import run_query
from app.graph.queries import (
    INCIDENT_ENTITIES,
    INCIDENT_MEMORIES,
    SIMILAR_INCIDENTS,
)
from app.ingestion.loader import upsert_node, upsert_rel
from app.models import MemoryIn, MemoryKind, normalize_ts
from app.models import MemoryOut

# Weights used for incident-to-incident similarity (same spirit as ranking).
_SIMILARITY_WEIGHTS = {
    "Account": 4.0,
    "Device": 3.0,
    "Process": 2.5,
    "Service": 2.0,
    "IPAddress": 1.0,
}


def _entity_set(incident_id: str) -> dict[str, float]:
    """Internal (discriminative) entities belonging to an incident's alerts."""
    rows = run_query(INCIDENT_ENTITIES, {"incident_id": incident_id})
    weights: dict[str, float] = {}
    for label, nid in rows:
        weights[nid] = _SIMILARITY_WEIGHTS.get(label, 1.0)
    return weights


def similarity(a_entities: dict[str, float], b_entities: dict[str, float]) -> tuple[float, list[str]]:
    """Weighted Jaccard similarity; returns (score, shared entity ids)."""
    if not a_entities or not b_entities:
        return 0.0, []
    shared = [k for k in a_entities if k in b_entities]
    union = set(a_entities) | set(b_entities)
    total_union = sum(b_entities.get(k, a_entities.get(k, 0.0)) for k in union)
    if total_union == 0:
        return 0.0, shared
    shared_weight = sum(a_entities[k] for k in shared)
    return round(shared_weight / total_union, 4), shared


def link_similar_incidents(incident_id: str, threshold: float) -> list[dict]:
    """Compute similarity to every other incident and persist SIMILAR_TO edges.

    Returns the linked incidents with score and shared-entity basis.
    """
    current = _entity_set(incident_id)
    others = run_query(
        "MATCH (i:Incident) WHERE i.id <> $id RETURN i.id",
        {"id": incident_id},
    )
    linked: list[dict] = []
    for (other_id,) in others:
        score, shared = similarity(current, _entity_set(other_id))
        if score < threshold or not shared:
            continue
        basis = f"shared entities: {', '.join(shared)} (weighted Jaccard)"
        upsert_rel(incident_id, "SIMILAR_TO", other_id, {"score": score, "basis": basis})
        linked.append({"id": other_id, "score": score, "basis": basis})
    linked.sort(key=lambda x: x["score"], reverse=True)
    return linked


def fetch_historical_context(incident_id: str, min_score: float) -> list[dict]:
    """Retrieve similar incidents + their stored memories with provenance."""
    rows = run_query(
        SIMILAR_INCIDENTS,
        {"incident_id": incident_id, "min_score": min_score},
    )
    contexts: list[dict] = []
    for other_id, props, score, basis in rows:
        mem_rows = run_query(INCIDENT_MEMORIES, {"incident_id": other_id})
        memories = [
            {
                "id": mid,
                "kind": mprops.get("kind"),
                "content": mprops.get("content"),
                "confidence": mprops.get("confidence"),
                "created_by": mprops.get("created_by"),
                "created_at": mprops.get("created_at"),
                "historical": bool(mprops.get("historical", False)),
                "trust_note": (
                    "Historical context from a previous investigation. "
                    "Treat as an unverified lead, not confirmed truth for the "
                    "current incident."
                ),
            }
            for mid, mprops in mem_rows
        ]
        contexts.append(
            {
                "similar_incident_id": other_id,
                "title": props.get("title", ""),
                "score": score,
                "basis": basis,
                "opened_at": props.get("opened_at"),
                "memories": memories,
            }
        )
    return contexts


def store_memory(mem: MemoryIn) -> MemoryOut:
    """Persist a finding or analyst feedback memory (+ provenance edges)."""
    import uuid

    mem_id = f"mem:{uuid.uuid4().hex[:16]}"
    created_at = normalize_ts(datetime.datetime.now(datetime.timezone.utc))
    props = {
        "kind": mem.kind.value,
        "content": mem.content,
        "confidence": mem.confidence,
        "created_at": created_at,
        "created_by": mem.created_by,
        "investigation_id": mem.investigation_id or "",
    }
    upsert_node("Memory", mem_id, props)
    if mem.incident_id:
        upsert_rel(mem_id, "PART_OF", mem.incident_id, {})
    if mem.investigation_id:
        upsert_rel(mem.investigation_id, "PRODUCED", mem_id, {"ts": created_at})
    # Analyst feedback / finding provenance edge.
    analyst_id = f"analyst:{mem.created_by.lstrip('@')}"
    upsert_node("Analyst", analyst_id, {"handle": mem.created_by})
    upsert_rel(analyst_id, "PRODUCED", mem_id, {"ts": created_at})

    return MemoryOut(
        id=mem_id,
        kind=mem.kind.value,
        content=mem.content,
        confidence=mem.confidence,
        incident_id=mem.incident_id,
        investigation_id=mem.investigation_id,
        created_by=mem.created_by,
        created_at=created_at,
    )


def list_memories(incident_id: str | None = None) -> list[MemoryOut]:
    if incident_id:
        rows = run_query(INCIDENT_MEMORIES, {"incident_id": incident_id})
    else:
        rows = run_query(
            "MATCH (m:Memory) RETURN m.id, properties(m) ORDER BY m.created_at DESC LIMIT 200"
        )
    return [
        MemoryOut(
            id=mid,
            kind=p.get("kind", MemoryKind.FINDING.value),
            content=p.get("content", ""),
            confidence=float(p.get("confidence", 0.5)),
            incident_id=None,
            investigation_id=p.get("investigation_id") or None,
            created_by=p.get("created_by", "unknown"),
            created_at=p.get("created_at", ""),
        )
        for mid, p in rows
    ]


def store_finding_for_incident(
    incident_id: str,
    investigation_id: str,
    content: str,
    confidence: float,
    created_by: str,
) -> MemoryOut:
    """Convenience wrapper used by the engine after each investigation."""
    return store_memory(
        MemoryIn(
            kind=MemoryKind.FINDING,
            content=content,
            confidence=confidence,
            incident_id=incident_id,
            investigation_id=investigation_id,
            created_by=created_by,
        )
    )

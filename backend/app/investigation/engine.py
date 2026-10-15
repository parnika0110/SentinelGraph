"""Graph-based investigation engine.

Pipeline (all retrieval happens in FalkorDB; nothing is fabricated):

  1. Load the seed alert and its INVOLVES/OBSERVED_ON entities.
  2. Bounded multi-hop traversal (CORRELATE_PATHS, max_traversal_hops) to find
     candidate alerts reachable through telemetry relationships only.
  3. Rank candidates with the transparent criteria in ranking.py (internal
     anchors required; external IPs never carry a group on their own).
  4. Extract the actual retrieved paths as Evidence nodes (immutable snapshots).
  5. Build observed facts (retrieved data), hypotheses (inference + confidence
     + missing evidence), and a deterministic evidence timeline.
  6. Persist an Incident with PART_OF/SUPPORTED_BY edges, link SIMILAR_TO to
     historical incidents, retrieve their stored Memory with provenance.
  7. Store a finding Memory, propose simulated actions (PROPOSED only).
  8. Optionally summarize via the LLM abstraction (never replaces retrieval).

GET /investigations/{id} later reconstructs the result from these persisted
graph artifacts, proving state survives separate requests/sessions.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.action_workflow import suggested_actions_for
from app.config import Settings, get_settings
from app.graph.connection import run_query
from app.graph.queries import CORRELATE_PATHS, GET_ALERT, ALERT_ENTITIES
from app.ingestion.loader import upsert_node, upsert_rel
from app.investigation.ranking import score_candidate
from app.llm import summarize
from app.memory import fetch_historical_context, link_similar_incidents, store_finding_for_incident
from app.models import (
    EvidenceItem,
    EvidencePath,
    HistoricalContext,
    Hypothesis,
    InvestigationResult,
    PathEdge,
    PathNode,
    normalize_ts,
)

_REL_TYPES_ALLOWED_FOR_GAP = {"CONNECTS_TO", "LOGGED_IN_FROM"}


def _now() -> str:
    return normalize_ts(datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Path <-> evidence conversion (falkordb client Path objects)
# ---------------------------------------------------------------------------

def path_to_evidence(path_obj) -> EvidencePath:
    path_nodes = list(path_obj.nodes())
    nodes = [
        PathNode(
            id=n.properties.get("id", str(n.id)),
            label=(n.labels[0] if n.labels else "Unknown"),
            props=dict(n.properties),
        )
        for n in path_nodes
    ]
    # FalkorDB Edge.src_node/dest_node are internal integer node ids; resolve
    # them back to graph ids via the nodes present on this path.
    id_by_internal: dict[int, str] = {
        int(n.id): n.properties.get("id", str(n.id)) for n in path_nodes
    }
    edges: list[PathEdge] = []
    for idx, e in enumerate(path_obj.edges()):
        src_int = getattr(e, "src_node", None)
        dst_int = getattr(e, "dest_node", None)
        if isinstance(src_int, int) and isinstance(dst_int, int):
            src = id_by_internal.get(src_int, "")
            dst = id_by_internal.get(dst_int, "")
        else:  # fallback: traversal order
            src = nodes[idx].id if idx < len(nodes) else ""
            dst = nodes[idx + 1].id if idx + 1 < len(nodes) else ""
        edges.append(
            PathEdge(
                type=getattr(e, "relation", "") or "",
                src=src,
                dst=dst,
                props=dict(getattr(e, "properties", {}) or {}),
            )
        )
    return EvidencePath(nodes=nodes, edges=edges)


def _path_ts(ev: EvidencePath) -> tuple[str | None, str | None]:
    stamps = [e.props.get("ts") for e in ev.edges if e.props.get("ts")]
    stamps += [n.props.get("ts") for n in ev.nodes if n.props.get("ts")]
    stamps = [s for s in stamps if s]
    if not stamps:
        return None, None
    return min(stamps), max(stamps)


def _describe_path(ev: EvidencePath) -> str:
    parts = []
    for e in ev.edges:
        ts = e.props.get("ts", "no timestamp")
        parts.append(f"{e.src} -[{e.type} @ {ts}]-> {e.dst}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_investigation(alert_id: str, analyst: str, settings: Settings | None = None) -> InvestigationResult:
    settings = settings or get_settings()
    notes: list[str] = []

    # 1) Seed alert ------------------------------------------------------
    rows = run_query(GET_ALERT, {"alert_id": alert_id})
    if not rows:
        raise KeyError(f"Alert {alert_id} not found")
    seed = rows[0][0]
    seed_props = dict(seed.properties)
    seed_ts = seed_props.get("ts")

    entity_rows = run_query(ALERT_ENTITIES, {"alert_id": alert_id})
    # ALERT_ENTITIES row: (label, id, entity_props, rel_type, rel_props)
    seed_entities = [
        {"label": r[0], "id": r[1], "props": r[2], "rel": r[3], "rel_props": r[4]}
        for r in entity_rows
    ]
    seed_entity_map: dict[str, tuple[str, dict]] = {
        r[1]: (r[0], r[2]) for r in entity_rows
    }

    # 2) Bounded traversal ----------------------------------------------
    hops = max(2, int(settings.max_traversal_hops))
    q = CORRELATE_PATHS.replace("__HOPS__", str(hops))
    corr_rows = run_query(q, {"alert_id": alert_id})
    notes.append(
        f"FalkorDB traversal: {len(corr_rows)} raw path(s) to other alerts within {hops} hops "
        f"(telemetry relationships only, meta nodes excluded)."
    )

    # 3) Convert + group paths per candidate alert ----------------------
    paths_by_candidate: dict[str, list[tuple[int, EvidencePath]]] = {}
    for path_obj, path_hops in corr_rows:
        ev = path_to_evidence(path_obj)
        if len(ev.nodes) < 3:  # must be a genuine multi-hop connection
            continue
        target = ev.nodes[-1].id
        paths_by_candidate.setdefault(target, []).append((int(path_hops), ev))

    evidence_items: list[EvidenceItem] = []
    evidence_by_candidate: dict[str, EvidenceItem] = {}
    excluded: list[dict] = []
    grouped: dict[str, dict] = {}

    for candidate_id, cand_paths in paths_by_candidate.items():
        cand_rows = run_query(GET_ALERT, {"alert_id": candidate_id})
        cand_props = dict(cand_rows[0][0].properties) if cand_rows else {}
        cand_ts = cand_props.get("ts")
        cand_entity_rows = run_query(ALERT_ENTITIES, {"alert_id": candidate_id})
        cand_entity_map: dict[str, tuple[str, dict]] = {
            r[1]: (r[0], r[2]) for r in cand_entity_rows
        }

        scored = [
            (
                hops_used,
                ev,
                score_candidate(
                    seed_entity_map,
                    cand_entity_map,
                    seed_ts,
                    cand_ts,
                    hops_used,
                    ev,
                    settings.correlation_threshold,
                ),
            )
            for hops_used, ev in cand_paths
        ]

        # Hard rule: historical archive alerts are context, never grouped.
        if cand_props.get("historical") is True:
            best = max(scored, key=lambda x: x[2]["total"])
            excluded.append(
                {
                    "alert_id": candidate_id,
                    "score": best[2]["total"],
                    "reason": (
                        "Excluded: historical archive alert (historical=true). "
                        "Surfaced as historical context instead of being grouped "
                        "into the live incident."
                    ),
                    "breakdown": best[2],
                }
            )
            notes.append(f"{candidate_id}: historical stub seen at {best[0]} hops - context only.")
            continue

        anchored = [s for s in scored if s[2]["internal_entity_ids"]]
        if not anchored:
            best = max(scored, key=lambda x: x[2]["total"])
            excluded.append(
                {
                    "alert_id": candidate_id,
                    "score": best[2]["total"],
                    "reason": best[2]["reason"],
                    "breakdown": best[2],
                }
            )
            notes.append(
                f"{candidate_id}: no internal anchor (only external IP share) - excluded."
            )
            continue

        best_hops, best_ev, best_score = max(anchored, key=lambda x: x[2]["total"])
        if not best_score["related"]:
            excluded.append(
                {
                    "alert_id": candidate_id,
                    "score": best_score["total"],
                    "reason": best_score["reason"],
                    "breakdown": best_score,
                }
            )
            continue

        grouped[candidate_id] = {
            "score": best_score,
            "hops": best_hops,
            "path": best_ev,
            "props": cand_props,
        }

        item = EvidenceItem(
            id=f"evi:{uuid.uuid4().hex[:12]}",
            kind="graph_path",
            summary=_describe_path(best_ev),
            path=best_ev,
            source_alert_ids=sorted({alert_id, candidate_id}),
            first_seen=_path_ts(best_ev)[0],
            last_seen=_path_ts(best_ev)[1],
            created_at=_now(),
        )
        evidence_items.append(item)
        evidence_by_candidate[candidate_id] = item

    # Seed context evidence (entities of the seed alert themselves) -------
    seed_ev = EvidencePath(
        nodes=[PathNode(id=alert_id, label="Alert", props=seed_props)]
        + [
            PathNode(id=r[1], label=r[0], props=r[2])
            for r in entity_rows
        ],
        edges=[
            PathEdge(
                type=r[3],
                src=alert_id,
                dst=r[1],
                props=r[4],
            )
            for r in entity_rows
        ],
    )
    seed_evidence = EvidenceItem(
        id=f"evi:{uuid.uuid4().hex[:12]}",
        kind="graph_path",
        summary=f"Seed alert context: {_describe_path(seed_ev) or 'no linked entities'}",
        path=seed_ev,
        source_alert_ids=[alert_id],
        first_seen=seed_ts,
        last_seen=seed_ts,
        created_at=_now(),
    )
    evidence_items.append(seed_evidence)

    related_alert_ids = sorted(grouped.keys())

    # 5) Observed facts vs hypotheses ------------------------------------
    observed_facts: list[str] = [
        f"Alert {alert_id} [{seed_props.get('severity')}] {seed_props.get('title')} "
        f"at {seed_ts} (source: {seed_props.get('source')})."
    ]
    for ent in seed_entities:
        observed_facts.append(
            f"{alert_id} -[{ent['rel']}]-> {ent['id']} "
            f"at {ent['rel_props'].get('ts', seed_ts)} (role: {ent['rel_props'].get('role', 'n/a')})."
        )
    for cid, g in grouped.items():
        observed_facts.append(
            f"Retrieved {g['hops']}-hop path {alert_id} ... {cid}: {_describe_path(g['path'])}"
        )

    hypotheses: list[Hypothesis] = []
    missing_evidence = _find_missing_evidence(alert_id, grouped, seed_entities)

    for idx, (cid, g) in enumerate(sorted(grouped.items()), start=1):
        score = g["score"]
        confidence = round(min(0.95, 0.30 + score["total"] / 12.0), 2)
        chain = " -> ".join(
            [n.id for n in g["path"].nodes]
        )
        hypotheses.append(
            Hypothesis(
                id=f"H{idx}",
                title=f"Continuation intrusion linking {alert_id} and {cid}",
                statement=(
                    f"The retrieved graph path {chain} connects the two alerts through "
                    f"shared internal entities ({', '.join(score['internal_entity_ids'])}) "
                    f"within {g['hops']} hops, with temporal proximity "
                    f"(temporal score {score['temporal_score']}) and activity edges "
                    f"[{', '.join(score['activity_types']) or 'inventory only'}]. "
                    f"This suggests {cid} is a continuation of the same intrusion, "
                    f"not an independent event."
                ),
                classification="hypothesis",
                confidence=confidence,
                supporting_evidence_ids=[evidence_by_candidate[cid].id],
                missing_evidence=missing_evidence,
                rationale=(
                    f"Score breakdown: entity={score['entity_score']}, "
                    f"temporal={score['temporal_score']}, "
                    f"activity={score['corroboration_score']}, "
                    f"hop_penalty={score['hop_penalty']} "
                    f"(threshold {score['threshold']}). Severity and shared "
                    f"public IPs contribute zero by policy."
                ),
            )
        )

    if not grouped:
        hypotheses.append(
            Hypothesis(
                id="H1",
                title="No correlated intrusion detected",
                statement=(
                    f"Within {hops} hops of {alert_id}, no other alert is connected "
                    "through internal entities. Candidate alerts were either "
                    "reachable only via non-discriminative external IPs or below "
                    "threshold. Treating this alert as a standalone event."
                ),
                classification="hypothesis",
                confidence=0.4,
                supporting_evidence_ids=[seed_evidence.id],
                missing_evidence=missing_evidence,
                rationale="Empty correlation result from bounded FalkorDB traversal.",
            )
        )

    # Timeline (assembled from retrieved timestamps only) -----------------
    timeline = _build_timeline(alert_id, seed_props, [e for e in evidence_items if e.path])

    # 6) Incident + persistence ------------------------------------------
    incident_id: str | None = None
    historical_context: list[HistoricalContext] = []
    investigation_id = f"inv:{uuid.uuid4().hex[:12]}"
    created_at = _now()

    # Materialize every evidence snapshot as an Evidence node (even when no
    # grouping occurs, so GET /investigations/{id} can reconstruct the run).
    for item in evidence_items:
        _persist_evidence_node(item, investigation_id)

    if grouped:
        incident_id = _ensure_incident(alert_id, related_alert_ids, investigation_id, created_at)
        for item in evidence_items:
            upsert_rel(incident_id, "SUPPORTED_BY", item.id, {"added_at": created_at})
            upsert_rel(investigation_id, "PRODUCED", item.id, {"ts": created_at})

        linked = link_similar_incidents(incident_id, settings.memory_similarity_threshold)
        if linked:
            notes.append(
                "Historical similarity links created: "
                + "; ".join(f"{l['id']} ({l['score']})" for l in linked)
            )
        historical_context = [
            HistoricalContext(**ctx)
            for ctx in fetch_historical_context(incident_id, settings.memory_similarity_threshold)
        ]

        top_score = max(g["score"]["total"] for g in grouped.values())
        finding = (
            f"Investigation of {alert_id} grouped {len(grouped)} related alert(s): "
            + ", ".join(related_alert_ids)
            + f". Strongest link score {top_score} via path(s) "
            + "; ".join(_describe_path(g["path"]) for g in grouped.values())
            + (f" Missing evidence: {'; '.join(missing_evidence)}" if missing_evidence else "")
        )
        store_finding_for_incident(
            incident_id, investigation_id, finding,
            confidence=round(min(0.95, 0.4 + top_score / 12.0), 2),
            created_by=analyst,
        )

    # 7) Suggested actions (PROPOSED only; approval is a separate step) ---
    account_ids = [e["id"] for e in seed_entities if e["label"] == "Account"]
    device_ids: list[str] = []
    external_ips: list[str] = []
    for g in grouped.values():
        for n in g["path"].nodes:
            if n.label == "Device" and n.id not in device_ids:
                device_ids.append(n.id)
            if (
                n.label == "IPAddress"
                and n.props.get("scope") == "external"
                and n.id not in external_ips
            ):
                external_ips.append(n.id)
    for e in seed_entities:
        if e["label"] == "Device" and e["id"] not in device_ids:
            device_ids.append(e["id"])
        if (
            e["label"] == "IPAddress"
            and e["props"].get("scope") == "external"
            and e["id"] not in external_ips
        ):
            external_ips.append(e["id"])

    suggested = []
    if incident_id:
        suggested = suggested_actions_for(
            incident_id=incident_id,
            seed_alert_id=alert_id,
            account_ids=account_ids,
            device_ids=device_ids,
            external_ip_ids=external_ips,
            evidence_ids=[i.id for i in evidence_items],
            created_by=analyst,
        )
        notes.append(f"{len(suggested)} simulated action(s) proposed (all require analyst approval).")

    # 8) Optional LLM summary over retrieved evidence only ----------------
    summary, provider = summarize(
        title=f"Investigation of {alert_id}: {seed_props.get('title', '')}",
        evidence_lines=[f.summary for f in evidence_items]
        + [f"Observed: {f}" for f in observed_facts[:6]],
        hypotheses=[h.statement for h in hypotheses],
        settings=settings,
    )
    notes.append(f"Summary provider: {provider}")

    result = InvestigationResult(
        id=investigation_id,
        seed_alert_id=alert_id,
        created_at=created_at,
        analyst=analyst,
        incident_id=incident_id,
        related_alert_ids=related_alert_ids,
        excluded_alert_ids=excluded,
        hypotheses=hypotheses,
        observed_facts=observed_facts,
        evidence=evidence_items,
        missing_evidence=missing_evidence,
        historical_context=historical_context,
        summary=summary,
        engine_notes=notes,
        timeline=timeline,
        suggested_actions=suggested,
    )
    _persist_investigation(result, seed_props)
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _persist_evidence_node(item: EvidenceItem, investigation_id: str) -> None:
    """Materialize an evidence snapshot as an immutable Evidence node."""
    upsert_node(
        "Evidence",
        item.id,
        {
            "kind": item.kind,
            "summary": item.summary,
            "path_json": json.dumps(item.path.model_dump(), default=str) if item.path else "",
            "source_alert_ids": item.source_alert_ids,
            "first_seen": item.first_seen,
            "last_seen": item.last_seen,
            "created_at": item.created_at,
            "investigation_id": investigation_id,
        },
    )


def _find_missing_evidence(
    seed_alert_id: str,
    grouped: dict[str, dict],
    seed_entities: list[dict],
) -> list[str]:
    """Deterministic gap detection -- each check is a real graph query/state."""
    gaps: list[str] = []

    # Does the seed account have authentication telemetry?
    has_account = any(e["label"] == "Account" for e in seed_entities)
    if has_account:
        acct_ids = [e["id"] for e in seed_entities if e["label"] == "Account"]
        for acct in acct_ids:
            n = run_query(
                "MATCH (a:Account {id: $id})-[l:LOGGED_IN_FROM]->() RETURN count(l)",
                {"id": acct},
            )[0][0]
            if n == 0:
                gaps.append(f"No authentication events (LOGGED_IN_FROM) retrieved for {acct}.")

    # Process telemetry coverage for devices on retrieved paths.
    devices: list[str] = [e["id"] for e in seed_entities if e["label"] == "Device"]
    for g in grouped.values():
        for n in g["path"].nodes:
            if n.label == "Device" and n.id not in devices:
                devices.append(n.id)
    for dev in devices:
        n = run_query(
            "MATCH (p:Process)-[r:RUNS]->(d:Device {id: $id}) RETURN count(r)",
            {"id": dev},
        )[0][0]
        if n == 0:
            gaps.append(
                f"No process-execution telemetry (RUNS) retrieved for {dev}; "
                "cannot confirm which process initiated its connections."
            )

    # Network flows without process attribution.
    for g in grouped.values():
        for edge in g["path"].edges:
            if edge.type == "CONNECTS_TO" and edge.src.startswith("dev:"):
                attributed = run_query(
                    "MATCH (p:Process)-[:CONNECTS_TO]->(t) WHERE t.id = $dst "
                    "RETURN count(p)",
                    {"dst": edge.dst},
                )[0][0]
                if attributed == 0:
                    gaps.append(
                        f"Flow {edge.src} -> {edge.dst} (port {edge.props.get('port', '?')}) "
                        "has no process attribution in the graph."
                    )

    # Deduplicate while preserving order.
    seen, unique = set(), []
    for g in gaps:
        if g not in seen:
            seen.add(g)
            unique.append(g)
    return unique


def _ensure_incident(
    seed_alert_id: str,
    related_alert_ids: list[str],
    investigation_id: str,
    created_at: str,
) -> str:
    """Create or reuse an Incident node for this grouping (deterministic id)."""
    existing = run_query(
        "MATCH (a:Alert {id: $id})-[:PART_OF]->(i:Incident) RETURN i.id LIMIT 1",
        {"id": seed_alert_id},
    )
    if existing:
        incident_id = existing[0][0]
    else:
        import hashlib

        digest = hashlib.sha1(
            "|".join(sorted([seed_alert_id] + related_alert_ids)).encode()
        ).hexdigest()[:6].upper()
        incident_id = f"INC-{datetime.now(timezone.utc).year}-{digest}"

    upsert_node(
        "Incident",
        incident_id,
        {
            "title": f"Correlated intrusion from {seed_alert_id}",
            "status": "OPEN",
            "severity": "high",
            "opened_at": created_at,
        },
    )
    for aid in [seed_alert_id] + related_alert_ids:
        upsert_rel(
            aid,
            "PART_OF",
            incident_id,
            {"grouped_at": created_at, "investigation_id": investigation_id},
        )
    return incident_id


def _build_timeline(seed_alert_id: str, seed_props: dict, evidence_items: list[EvidenceItem]) -> list[dict]:
    """Chronological events from retrieved timestamps only."""
    events: list[dict] = [
        {
            "ts": seed_props.get("ts"),
            "kind": "alert",
            "text": f"Seed alert {seed_alert_id}: {seed_props.get('title')}",
            "source_alert_ids": [seed_alert_id],
            "observed": True,
        }
    ]
    seen_pairs: set[tuple] = set()
    for item in evidence_items:
        if not item.path:
            continue
        for edge in item.path.edges:
            ts = edge.props.get("ts")
            if not ts:
                continue
            key = (ts, edge.type, edge.src, edge.dst)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            events.append(
                {
                    "ts": ts,
                    "kind": "relationship",
                    "text": f"{edge.src} -[{edge.type}]-> {edge.dst}",
                    "detail": json.dumps(edge.props, default=str),
                    "source_alert_ids": item.source_alert_ids,
                    "observed": True,
                }
            )
        for node in item.path.nodes:
            if node.label == "Alert" and node.props.get("ts"):
                key = (node.props["ts"], "alert", node.id)
                if key in seen_pairs or node.id == seed_alert_id:
                    continue
                seen_pairs.add(key)
                events.append(
                    {
                        "ts": node.props["ts"],
                        "kind": "alert",
                        "text": f"{node.id}: {node.props.get('title', '')}",
                        "source_alert_ids": [node.id],
                        "observed": True,
                    }
                )
    events = [e for e in events if e.get("ts")]
    events.sort(key=lambda e: e["ts"])
    return events


def _persist_investigation(result: InvestigationResult, seed_props: dict) -> None:
    upsert_node(
        "Investigation",
        result.id,
        {
            "id": result.id,
            "seed_alert_id": result.seed_alert_id,
            "created_at": result.created_at,
            "analyst": result.analyst,
            "incident_id": result.incident_id or "",
            "summary": result.summary,
            "related_alert_ids": result.related_alert_ids,
            "excluded_alerts_json": json.dumps(result.excluded_alert_ids, default=str),
            "hypotheses_json": json.dumps([h.model_dump() for h in result.hypotheses]),
            "observed_facts": result.observed_facts,
            "evidence_ids": [e.id for e in result.evidence],
            "missing_evidence": result.missing_evidence,
            "engine_notes": result.engine_notes,
            "timeline_json": json.dumps(result.timeline, default=str),
            "historical_context_json": json.dumps(
                [h.model_dump() for h in result.historical_context], default=str
            ),
        },
    )


# ---------------------------------------------------------------------------
# Reconstruction for GET /investigations/{id}
# ---------------------------------------------------------------------------

def get_investigation(investigation_id: str) -> InvestigationResult | None:
    """Rebuild an investigation result from persisted graph artifacts."""
    rows = run_query("MATCH (i:Investigation {id: $id}) RETURN properties(i)", {"id": investigation_id})
    if not rows:
        return None
    props = rows[0][0]

    evidence_ids: list[str] = list(props.get("evidence_ids") or [])
    evidence: list[EvidenceItem] = []
    for eid in evidence_ids:
        erows = run_query(
            "MATCH (e:Evidence {id: $id}) RETURN properties(e)", {"id": eid}
        )
        if not erows:
            continue
        ep = erows[0][0]
        path = None
        if ep.get("path_json"):
            path = EvidencePath(**json.loads(ep["path_json"]))
        evidence.append(
            EvidenceItem(
                id=eid,
                kind=ep.get("kind", "graph_path"),
                summary=ep.get("summary", ""),
                path=path,
                source_alert_ids=list(ep.get("source_alert_ids") or []),
                first_seen=ep.get("first_seen"),
                last_seen=ep.get("last_seen"),
                created_at=ep.get("created_at", ""),
            )
        )

    incident_id = props.get("incident_id") or None
    historical: list[HistoricalContext] = []
    if incident_id:
        historical = [
            HistoricalContext(**ctx)
            for ctx in fetch_historical_context(
                incident_id, get_settings().memory_similarity_threshold
            )
        ]

    from app.action_workflow import list_actions

    actions = list_actions(incident_id) if incident_id else []

    return InvestigationResult(
        id=investigation_id,
        seed_alert_id=props.get("seed_alert_id", ""),
        created_at=props.get("created_at", ""),
        analyst=props.get("analyst", "unknown"),
        incident_id=incident_id,
        related_alert_ids=list(props.get("related_alert_ids") or []),
        excluded_alert_ids=json.loads(props.get("excluded_alerts_json") or "[]"),
        hypotheses=[Hypothesis(**h) for h in json.loads(props.get("hypotheses_json") or "[]")],
        observed_facts=list(props.get("observed_facts") or []),
        evidence=evidence,
        missing_evidence=list(props.get("missing_evidence") or []),
        historical_context=historical,
        summary=props.get("summary", ""),
        engine_notes=list(props.get("engine_notes") or []),
        timeline=json.loads(props.get("timeline_json") or "[]"),
        suggested_actions=actions,
    )

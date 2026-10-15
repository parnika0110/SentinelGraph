"""Transparent ranking of candidate alert correlations.

Every criterion below is computed from retrieved graph data only. Nothing here
calls an LLM and nothing invents evidence: if a relationship was not retrieved
from FalkorDB, it contributes nothing.

CORE RULE (why two alerts are connected at all)
A candidate path is a chain seed -> m1 -> ... -> mk -> candidate. The alerts
are only as well-connected as:

  (a) SHARED ENTITIES (direct_shared_score): entities attached to BOTH alerts
      (2-hop), weights: Account 4.0, Device 3.0, Process 2.5, Service 2.0,
      internal IPAddress 1.0. External IPs never count -- sharing a public IP
      is a generic attribute, never a correlation.

  (b) THE CRITICAL BRIDGE (bridge_score): the path must CROSS from the
      seed's own entities to the candidate's own entities. A bridge edge is a
      consecutive intermediate pair (u, v) where one endpoint is a direct
      entity of the seed alert and the other is a direct entity of the
      candidate alert. The pair contributes min(weight) when their edge is
      observed activity (LOGGED_IN_FROM/RUNS/CONNECTS_TO), or half that for
      inventory edges (USED/DEPENDS_ON).

      Two things this rules out:
      - If either endpoint is an external IP, the crossing is
        non-discriminative and scores 0 regardless of internal topology
        elsewhere on the path.
      - Topology that only touches ONE of the two alerts (e.g. the seed's own
        account-device chain while the candidate attaches via an external IP)
        is never a bridge, because no seed->candidate crossing exists there.

This is precisely what prevents "A and C both touched 203.0.113.44" from
grouping: any path into C crosses through the external IP as its last hop.

REMAINING CRITERIA
1. entity_score = direct_shared_score + bridge_score (per path).
2. HISTORICAL HARD RULE: alerts flagged historical=true are context only.
3. hop_penalty: -0.5 per hop beyond the minimum 2.
4. temporal_score: |ts(seed)-ts(candidate)|: <=1h +2.0, <=6h +1.5, <=24h +1.0,
   <=7d +0.5, else 0. Timestamps come from the alert nodes.
5. corroboration_score: +1.0 if the path contains an observed-activity
   relationship beyond static inventory edges.
6. WHAT SCORES ZERO: severity equality, sharing a public IP, alert source/tags.

total = entity_score + temporal_score + corroboration_score + hop_penalty
Group iff total >= correlation_threshold (default 3.0) AND entity_score > 0;
everything else is returned as an exclusion with a human-readable reason.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models import EvidencePath

# Entity type weights for internal anchors.
ENTITY_WEIGHTS: dict[str, float] = {
    "Account": 4.0,
    "Device": 3.0,
    "Process": 2.5,
    "Service": 2.0,
    "IPAddress": 1.0,  # internal scope only (checked below)
}

# Relationships that count as observed activity (vs static inventory).
ACTIVITY_REL_TYPES = {"LOGGED_IN_FROM", "RUNS", "CONNECTS_TO"}

# Inventory / alert-scaffolding relationships (no activity by themselves).
INVENTORY_REL_TYPES = {"INVOLVES", "OBSERVED_ON", "USED", "DEPENDS_ON"}


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def temporal_score(seed_ts: str | None, candidate_ts: str | None) -> float:
    a, b = _parse_ts(seed_ts), _parse_ts(candidate_ts)
    if not a or not b:
        return 0.0
    delta_hours = abs((a - b).total_seconds()) / 3600.0
    if delta_hours <= 1:
        return 2.0
    if delta_hours <= 6:
        return 1.5
    if delta_hours <= 24:
        return 1.0
    if delta_hours <= 24 * 7:
        return 0.5
    return 0.0


def _weight(label: str, node_id: str, props: dict) -> float:
    """Weight of a node; 0 for external IPs (non-discriminative)."""
    if label == "IPAddress":
        return 0.0 if props.get("scope", "external") == "external" else ENTITY_WEIGHTS["IPAddress"]
    return ENTITY_WEIGHTS.get(label, 0.0)


def score_candidate(
    seed_entities: dict[str, tuple[str, dict]],
    candidate_entities: dict[str, tuple[str, dict]],
    seed_ts: str | None,
    candidate_ts: str | None,
    hops: int,
    path: EvidencePath,
    correlation_threshold: float,
) -> dict:
    """Score one candidate alert against the seed alert for one retrieved path.

    seed_entities/candidate_entities: {node_id: (label, props)} of each
    alert's direct INVOLVES/OBSERVED_ON neighbors (retrieved from FalkorDB).
    """
    intermediates = path.nodes[1:-1]

    # (a) shared discriminative entities (present on this evidence path)
    shared_ids: list[str] = []
    shared_score = 0.0
    for nid, (label, props) in seed_entities.items():
        if nid in candidate_entities and nid in {n.id for n in intermediates}:
            w = _weight(label, nid, props)
            if w > 0:
                shared_ids.append(nid)
                shared_score += w

    # (b) critical bridge: the seed-side -> candidate-side crossing edge(s).
    seed_ids = set(seed_entities)
    cand_ids = set(candidate_entities)
    bridge_ids: list[str] = []
    bridge_score = 0.0
    external_ip_ids: list[str] = []
    if len(intermediates) >= 2:
        for i in range(len(intermediates) - 1):
            u, v = intermediates[i], intermediates[i + 1]
            u_seed, v_seed = u.id in seed_ids, v.id in seed_ids
            u_cand, v_cand = u.id in cand_ids, v.id in cand_ids
            if not ((u_seed and v_cand) or (u_cand and v_seed)):
                continue  # this pair does not cross between the two alerts
            w_u = _weight(u.label, u.id, u.props)
            w_v = _weight(v.label, v.id, v.props)
            if w_u <= 0 or w_v <= 0:
                continue  # crossing through an external IP is never a bridge
            edge_type = ""
            for e in path.edges:
                if {e.src, e.dst} == {u.id, v.id}:
                    edge_type = e.type
                    break
            if edge_type in ACTIVITY_REL_TYPES:
                score = min(w_u, w_v)
            elif edge_type in INVENTORY_REL_TYPES:
                score = min(w_u, w_v) * 0.5
            else:
                score = 0.0
            if score > bridge_score:
                bridge_score = score
                bridge_ids = [u.id, v.id]

    # external IPs on the path (for the exclusion reason text)
    for n in path.nodes:
        if n.label == "IPAddress" and n.props.get("scope", "external") == "external":
            if n.id not in external_ip_ids:
                external_ip_ids.append(n.id)

    # intermediate internal ids used anywhere (for display)
    internal_on_path = [
        n.id
        for n in intermediates
        if _weight(n.label, n.id, n.props) > 0 and n.id not in shared_ids
    ]

    entity_score = shared_score + bridge_score
    hop_penalty = -0.5 * max(0, hops - 2)
    t_score = temporal_score(seed_ts, candidate_ts)
    activity_types = sorted({e.type for e in path.edges if e.type in ACTIVITY_REL_TYPES})
    c_score = 1.0 if activity_types else 0.0
    total = entity_score + t_score + c_score + hop_penalty

    internal_entity_ids = list(dict.fromkeys(shared_ids + internal_on_path + bridge_ids))

    breakdown = {
        "entity_score": round(entity_score, 2),
        "shared_entity_score": round(shared_score, 2),
        "bridge_score": round(bridge_score, 2),
        "temporal_score": t_score,
        "corroboration_score": c_score,
        "hop_penalty": hop_penalty,
        "total": round(total, 2),
        "threshold": correlation_threshold,
        "shared_entity_ids": shared_ids,
        "internal_entity_ids": internal_entity_ids,
        "bridge_edge_ids": bridge_ids,
        "external_ip_ids": external_ip_ids,
        "activity_types": activity_types,
        "hops": hops,
    }

    if entity_score <= 0:
        reason = (
            "Excluded: no discriminative connection. Every retrieved path into "
            "this alert crosses through non-discriminative external IP address(es) "
            f"{external_ip_ids or ['(none)']} as its final hop; the alerts share no "
            "internal entities. Sharing a public IP (or a severity level) never "
            "justifies grouping."
        )
        return {**breakdown, "related": False, "reason": reason}

    if total < correlation_threshold:
        reason = (
            f"Excluded: score {round(total, 2)} < threshold {correlation_threshold} "
            f"(entity={breakdown['entity_score']}, temporal={t_score}, "
            f"activity={c_score}, hops={hop_penalty})."
        )
        return {**breakdown, "related": False, "reason": reason}

    basis = []
    if shared_ids:
        basis.append(f"shared entities {', '.join(shared_ids)}")
    if bridge_ids:
        basis.append(f"internal bridge {' -> '.join(bridge_ids)}")
    reason = (
        f"Grouped: score {round(total, 2)} >= {correlation_threshold} via "
        f"{'; '.join(basis)} ({hops} hops, activity edges: "
        f"{', '.join(activity_types) or 'inventory only'})."
    )
    return {**breakdown, "related": True, "reason": reason}

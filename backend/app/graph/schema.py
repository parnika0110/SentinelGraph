"""Graph schema for SentinelGraph.

FalkorDB is the core reasoning and memory layer: every fact the investigation
engine uses (entities, telemetry observations, alert provenance, historical
findings, analyst decisions) lives in the graph and is retrieved with Cypher.

================================================================================
NODE LABELS
================================================================================
Alert       A security alert (id = source alert id, e.g. "ALR-2026-10-0011").
            Props: title, description, severity, alert_type, ts, source.
Account     Identity (user/service account).        id "acct:<name>"
Device      Endpoint or server.                     id "dev:<hostname>"
IPAddress   IPv4/6 address. Props include scope ("external"|"internal").
            id "ip:<addr>"
Process     Process observed on a device (name, sha256, command_line).
            id "proc:<slug>"
Service     Software service.                       id "svc:<name>"
Incident    A grouped investigation case.           id "INC-<year>-<seq>"
Evidence    A materialized, immutable snapshot of retrieved graph evidence
            (a real path with nodes, relationships and timestamps).
            id "EVI-<seq>". Props: kind, path_json, summary, created_at.
Analyst     Human operator.                         id "analyst:<handle>"
Memory      Persistent investigation memory (finding or analyst feedback).
            Props: kind ("finding"|"feedback"), content, confidence,
            created_at, created_by, investigation_id.
Action      Simulated response action. Props: action_type, target_id,
            description, status (PROPOSED|APPROVED|REJECTED|COMPLETED),
            created_at, decided_at, created_by, evidence_ids.
Investigation  One executed investigation run (extension label).
            Props: id, seed_alert_id, created_at, summary, hypotheses_json,
            related_alert_ids, missing_evidence.

================================================================================
RELATIONSHIPS (all only created when backed by synthetic evidence)
================================================================================
(Alert)-[:INVOLVES]->(Account|Device|IPAddress|Process|Service)
    The alert involves an entity. Rel props: role, ts, alert_id (provenance).
(Alert)-[:OBSERVED_ON]->(Device)
    The alert fired on a specific endpoint. Props: ts, alert_id.
(Account)-[:USED]->(Device)
    Inventory/identity association between an account and a device.
    Props: first_seen, last_seen, source.
(Account)-[:LOGGED_IN_FROM]->(IPAddress)
    Authentication event. Props: ts, success, source.
(Process)-[:RUNS]->(Device)
    Process execution on a device (EDR telemetry). Props: ts, command_line.
(Process)-[:CONNECTS_TO]->(IPAddress)
    Outbound network connection from a process. Props: ts, port, proto.
(Device)-[:CONNECTS_TO]->(Device|IPAddress)
    Network flow between endpoints/IPs. Props: ts, port, proto.
(Service)-[:DEPENDS_ON]->(Service)
    Service dependency. Props: source.
(Service)-[:RUNS]->(Device)
    Service hosted on a device.
(Alert)-[:PART_OF]->(Incident)
    Alert grouped into an incident by the investigation engine.
    Props: grouped_at, investigation_id, score.
(Incident)-[:SUPPORTED_BY]->(Evidence)
    Incident findings are backed by materialized evidence.
(Incident)-[:SIMILAR_TO]->(Incident)
    Computed similarity to a historical incident. Props: score, basis.
(Analyst)-[:INVESTIGATED]->(Incident)
    Analyst worked the incident. Props: started_at.
(Investigation)-[:PRODUCED]->(Evidence|Memory)
    Provenance: which investigation run produced which evidence/memory.
(Analyst)-[:PRODUCED]->(Memory)
    Analyst feedback memory provenance. Props: ts.
(Memory)-[:PART_OF]->(Incident)
    Memory belongs to an incident's knowledge record.
(Action)-[:PROPOSED_FOR]->(Incident)
    Proposed simulated action. Props: proposed_at, evidence_ids.
(Action)-[:APPROVED_BY]->(Analyst)
    Approval/rejection decision. Props: decision, decided_at, reason.

================================================================================
RANKING / NON-FABRICATION RULES (implemented in investigation/ranking.py)
================================================================================
* Traversals are bounded (max_traversal_hops) and restricted to telemetry
  relationship types -- never through Incident/Memory/Evidence/Action nodes,
  so grouping cannot become self-referential.
* External IPAddress nodes are non-discriminative anchors: sharing one
  (e.g. a public source IP) never groups alerts by itself.
* Every returned hypothesis must cite at least one real retrieved path;
  the engine never fabricates paths or evidence.
"""

from __future__ import annotations

from app.graph.connection import run_query

NODE_LABELS = [
    "Alert",
    "Account",
    "Device",
    "IPAddress",
    "Process",
    "Service",
    "Incident",
    "Evidence",
    "Analyst",
    "Memory",
    "Action",
    "Investigation",
]

RELATIONSHIP_TYPES = [
    "INVOLVES",
    "OBSERVED_ON",
    "USED",
    "LOGGED_IN_FROM",
    "RUNS",
    "CONNECTS_TO",
    "DEPENDS_ON",
    "PART_OF",
    "SUPPORTED_BY",
    "SIMILAR_TO",
    "INVESTIGATED",
    "PRODUCED",
    "PROPOSED_FOR",
    "APPROVED_BY",
]

# Relationship types the correlation traversal is allowed to follow.
TELEMETRY_REL_TYPES = [
    "INVOLVES",
    "OBSERVED_ON",
    "USED",
    "LOGGED_IN_FROM",
    "RUNS",
    "CONNECTS_TO",
    "DEPENDS_ON",
]

# Labels that must never be traversed through during correlation.
META_LABELS = ["Incident", "Memory", "Evidence", "Action", "Investigation"]

# Labels that get a uniqueness index on :id.
INDEXED_LABELS = [
    "Alert",
    "Account",
    "Device",
    "IPAddress",
    "Process",
    "Service",
    "Incident",
    "Evidence",
    "Analyst",
    "Memory",
    "Action",
    "Investigation",
]


def ensure_schema(settings=None) -> dict:
    """Create id indexes on every node label (idempotent).

    FalkorDB supports `CREATE INDEX FOR (n:Label) ON (n.id)`; we fall back to
    the legacy `CREATE INDEX ON :Label(id)` syntax for older images.
    """
    created, skipped = [], []
    for label in INDEXED_LABELS:
        try:
            run_query(f"CREATE INDEX FOR (n:{label}) ON (n.id)", settings=settings)
            created.append(label)
        except Exception as exc:  # index may already exist
            msg = str(exc).lower()
            if "already" in msg or "exist" in msg or "equivalent" in msg:
                skipped.append(label)
            else:
                # Try legacy syntax before giving up.
                try:
                    run_query(f"CREATE INDEX ON :{label}(id)", settings=settings)
                    created.append(label)
                except Exception as exc2:
                    msg2 = str(exc2).lower()
                    if "already" in msg2 or "exist" in msg2 or "equivalent" in msg2:
                        skipped.append(label)
                    else:
                        raise
    return {"created": created, "already_existed": skipped}


def schema_document() -> dict:
    """Machine-readable schema description (served by GET /graph/schema)."""
    return {
        "node_labels": NODE_LABELS,
        "relationship_types": RELATIONSHIP_TYPES,
        "traversal_relationship_types": TELEMETRY_REL_TYPES,
        "excluded_traversal_labels": META_LABELS,
        "doc": __doc__,
    }

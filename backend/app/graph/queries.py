"""Shared parameterized Cypher queries.

Centralising queries keeps them auditable: every query here uses bound
parameters ($name) -- no user input is ever interpolated into Cypher.
"""

from __future__ import annotations

from app.graph.schema import META_LABELS, TELEMETRY_REL_TYPES

# --- labels/rel-types as Cypher literals (from constants only, never user input)
_TELEMETRY_LIST = "[" + ", ".join(f"'{t}'" for t in TELEMETRY_REL_TYPES) + "]"
_META = "|".join(META_LABELS)

# ---------------------------------------------------------------------------
# Generic upserts
# ---------------------------------------------------------------------------

UPSERT_NODE="""
MERGE (n:`{label}` {{id: $id}})
SET n += $props
RETURN n.id AS id
"""

# Creates a node only if the id is new (never overwrites existing properties).
UPSERT_NODE_ON_CREATE="""
MERGE (n:`{label}` {{id: $id}})
ON CREATE SET n += $props
RETURN n.id AS id
"""

CREATE_REL = """
MATCH (a {{id: $src_id}})
MATCH (b {{id: $dst_id}})
MERGE (a)-[r:`{rel}`]->(b)
SET r += $props
RETURN type(r) AS rel
"""

# Timestamped event edges (login/run/flow): uniqueness includes the event
# timestamp, so distinct events become parallel edges with their own
# provenance instead of overwriting one another. Idempotent per event.
CREATE_EVENT_REL = """
MATCH (a {{id: $src_id}})
MATCH (b {{id: $dst_id}})
MERGE (a)-[r:`{rel}` {{ts: $props.ts}}]->(b)
SET r += $props
RETURN type(r) AS rel
"""

# ---------------------------------------------------------------------------
# Alert context
# ---------------------------------------------------------------------------

GET_ALERT = """
MATCH (a:Alert {id: $alert_id})
RETURN a
"""

ALERT_ENTITIES = """
MATCH (a:Alert {id: $alert_id})-[r:INVOLVES|OBSERVED_ON]->(e)
RETURN labels(e)[0] AS label, e.id AS id, properties(e) AS props,
       type(r) AS rel, properties(r) AS rel_props
"""

# ---------------------------------------------------------------------------
# Correlation: bounded multi-hop traversal from the seed alert to other alerts.
# Follows telemetry relationships only and never traverses through meta nodes
# (Incident/Memory/Evidence/Action/Investigation) to avoid self-referential
# grouping. Returns full paths for provenance.
# ---------------------------------------------------------------------------
# NOTE: hop bounds are integers validated in Python before being substituted
# for the __HOPS__ token; relationship/node label lists come from constants only.
# FalkorDB quirks handled here (verified against a live server):
#   * ALL(r IN rs ...) on a variable-length match var fails ("expected List but
#     was Path") -> iterate relationships(path) instead.
#   * nodes(path)[1..-1] slicing fails inside predicates -> range() indexing.
#   * Intermediate nodes must be entities only: no other Alert (avoids chaining
#     through third alerts) and no meta nodes (avoids self-referential grouping).

CORRELATE_PATHS = f"""
MATCH path = (seed:Alert {{id: $alert_id}})-[rs*2..__HOPS__]-(other:Alert)
WHERE other.id <> $alert_id
  AND ALL(r IN relationships(path) WHERE type(r) IN {_TELEMETRY_LIST})
  AND ALL(i IN range(1, size(nodes(path))-2)
      WHERE NOT (nodes(path)[i]:Alert OR nodes(path)[i]:Incident
              OR nodes(path)[i]:Memory OR nodes(path)[i]:Evidence
              OR nodes(path)[i]:Action OR nodes(path)[i]:Investigation))
RETURN path, length(path) AS hops
LIMIT 200
"""

# Direct (1-hop through one shared entity) convenience query.
CORRELATE_SHARED_ENTITIES = f"""
MATCH (seed:Alert {{id: $alert_id}})-[:INVOLVES|OBSERVED_ON]->(e)
      <-[:INVOLVES|OBSERVED_ON]-(other:Alert)
WHERE other.id <> $alert_id
  AND NOT (e:{_META.replace('|', ' OR e:')})
RETURN DISTINCT other.id AS alert_id, labels(e)[0] AS entity_label,
       e.id AS entity_id, properties(e) AS entity_props
"""

# ---------------------------------------------------------------------------
# Neighborhood extraction for the graph explorer
# ---------------------------------------------------------------------------
# hop bounds formatted after int validation.

NEIGHBORHOOD = """
MATCH (n {id: $id})
OPTIONAL MATCH (n)-[r]-(m)
RETURN n, type(r) AS rel, properties(r) AS rel_props, m
LIMIT $limit
"""

# ---------------------------------------------------------------------------
# Incidents / memory
# ---------------------------------------------------------------------------

SIMILAR_INCIDENTS = f"""
MATCH (inc:Incident {{id: $incident_id}})-[s:SIMILAR_TO]->(old:Incident)
WHERE s.score >= $min_score
RETURN old.id AS id, properties(old) AS props, s.score AS score, s.basis AS basis
ORDER BY s.score DESC
"""

INCIDENT_MEMORIES = """
MATCH (mem:Memory)-[:PART_OF]->(inc:Incident {id: $incident_id})
RETURN mem.id AS id, properties(mem) AS props
ORDER BY mem.created_at DESC
"""

INCIDENT_ALERTS = """
MATCH (a:Alert)-[:PART_OF]->(inc:Incident {id: $incident_id})
RETURN a.id AS id, properties(a) AS props
ORDER BY a.ts ASC
"""

INCIDENT_EVIDENCE = """
MATCH (inc:Incident {id: $incident_id})-[:SUPPORTED_BY]->(ev:Evidence)
RETURN ev.id AS id, properties(ev) AS props
ORDER BY ev.created_at ASC
"""

INCIDENT_ACTIONS = """
MATCH (act:Action)-[:PROPOSED_FOR]->(inc:Incident {id: $incident_id})
OPTIONAL MATCH (act)-[ap:APPROVED_BY]->(an:Analyst)
RETURN act.id AS id, properties(act) AS props,
       an.id AS analyst_id, ap.decision AS decision, ap.reason AS reason,
       ap.decided_at AS decided_at
ORDER BY act.created_at ASC
"""

# Entity inventory used for similarity computation (non-generic entities only).
INCIDENT_ENTITIES = f"""
MATCH (inc:Incident {{id: $incident_id}})<-[:PART_OF]-(a:Alert)
MATCH (a)-[:INVOLVES|OBSERVED_ON]->(e)
WHERE NOT (e:{_META.replace('|', ' OR e:')})
  AND NOT (e:IPAddress AND e.scope = 'external')
RETURN DISTINCT labels(e)[0] AS label, e.id AS id
"""

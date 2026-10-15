"""Graph explorer endpoints.

GET /graph/neighborhood/{id} -- bounded neighborhood subgraph (nodes + edges)
GET /graph/schema            -- documented schema (labels, rel types, rules)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.graph.connection import run_query
from app.graph.schema import schema_document
from app.models import GraphEdge, GraphNode, NeighborhoodResponse

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/neighborhood/{node_id}", response_model=NeighborhoodResponse)
def neighborhood(
    node_id: str,
    hops: int = Query(1, ge=1, le=4, description="Traversal depth (1-4)"),
) -> NeighborhoodResponse:
    """BFS neighborhood around a node using parameterized queries.

    Used by the interactive graph explorer: returns real nodes and relationships
    from FalkorDB (never synthesized on the client).
    """
    center = run_query("MATCH (n {id: $id}) RETURN n", {"id": node_id})
    if not center:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    nodes: dict[str, GraphNode] = {}
    edges: dict[str, GraphEdge] = {}

    def add_node(node) -> None:
        props = dict(node.properties)
        nid = props.get("id", str(node.id))
        if nid not in nodes:
            nodes[nid] = GraphNode(
                id=nid,
                label=(node.labels[0] if node.labels else "Unknown"),
                props=props,
            )

    add_node(center[0][0])
    frontier = [node_id]
    for _ in range(hops):
        if not frontier:
            break
        rows = run_query(
            "MATCH (a)-[r]-(b) WHERE a.id IN $frontier "
            "RETURN a, type(r), properties(r), b, properties(b)",
            {"frontier": frontier},
        )
        next_frontier: list[str] = []
        for a, rel_type, rel_props, b, b_props in rows:
            add_node(a)
            add_node(b)
            a_id = dict(a.properties).get("id", str(a.id))
            b_id = dict(b.properties).get("id", str(b.id))
            for src, dst in ((a_id, b_id), (b_id, a_id)):
                key = f"{rel_type}:{src}->{dst}" if (src, dst) == (a_id, b_id) else f"{rel_type}:{dst}->{src}"
                if key not in edges:
                    edges[key] = GraphEdge(
                        id=f"e:{key}",
                        type=rel_type,
                        src=src,
                        dst=dst,
                        props=dict(rel_props or {}),
                    )
            if b_id not in frontier and len(nodes) < 400:
                next_frontier.append(b_id)
        frontier = list(dict.fromkeys(next_frontier))

    return NeighborhoodResponse(
        center_id=node_id, hops=hops, nodes=list(nodes.values()), edges=list(edges.values())
    )


@router.get("/schema")
def get_schema() -> dict:
    return schema_document()

"""Memory endpoints: store findings/analyst feedback, list with provenance.

POST /memories        -- persist a finding or analyst feedback (with provenance)
GET  /memories        -- list stored memories (optionally by incident)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.memory import list_memories, store_memory
from app.models import MemoryIn, MemoryOut

router = APIRouter(tags=["memory"])


@router.post("/memories", response_model=MemoryOut, status_code=201)
def create_memory(mem: MemoryIn) -> MemoryOut:
    """Persist investigation memory (kind=finding|feedback) in FalkorDB."""
    if mem.incident_id:
        from app.graph.connection import run_query

        exists = run_query(
            "MATCH (i:Incident {id: $id}) RETURN i.id", {"id": mem.incident_id}
        )
        if not exists:
            raise HTTPException(
                status_code=404, detail=f"Incident {mem.incident_id} not found"
            )
    return store_memory(mem)


@router.get("/memories")
def get_memories(incident_id: str | None = Query(None)) -> dict:
    items = list_memories(incident_id)
    return {"count": len(items), "memories": [m.model_dump() for m in items]}

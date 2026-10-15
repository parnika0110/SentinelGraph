"""FalkorDB connection management.

A thin, thread-safe wrapper around the official FalkorDB Python client.
All Cypher in this project is executed through `run_query` with bound
parameters -- never with string interpolation of user input.
"""

from __future__ import annotations

import threading
from typing import Any

from falkordb import FalkorDB

from app.config import Settings, get_settings

_lock = threading.Lock()
_client: FalkorDB | None = None


def get_client(settings: Settings | None = None) -> FalkorDB:
    """Return a process-wide FalkorDB client (created lazily)."""
    global _client
    settings = settings or get_settings()
    with _lock:
        if _client is None:
            kwargs: dict[str, Any] = {"host": settings.falkordb_host, "port": settings.falkordb_port}
            if settings.falkordb_username:
                kwargs["username"] = settings.falkordb_username
            if settings.falkordb_password:
                kwargs["password"] = settings.falkordb_password
            _client = FalkorDB(**kwargs)
        return _client


def get_graph(graph_name: str | None = None, settings: Settings | None = None):
    """Return a handle to the named graph."""
    settings = settings or get_settings()
    return get_client(settings).select_graph(graph_name or settings.graph_name)


def run_query(
    cypher: str,
    params: dict[str, Any] | None = None,
    graph_name: str | None = None,
    settings: Settings | None = None,
) -> list[list[Any]]:
    """Execute a parameterized Cypher query and return the result rows."""
    graph = get_graph(graph_name, settings)
    result = graph.query(cypher, params=params or {})
    return result.result_set


def run_query_with_stats(
    cypher: str,
    params: dict[str, Any] | None = None,
    graph_name: str | None = None,
    settings: Settings | None = None,
) -> tuple[list[list[Any]], dict[str, Any]]:
    """Execute a query and return (rows, statistics)."""
    graph = get_graph(graph_name, settings)
    result = graph.query(cypher, params=params or {})
    return result.result_set, dict(result.statistics)


def drop_graph(graph_name: str, settings: Settings | None = None) -> None:
    """Delete an entire graph (used by tests)."""
    graph = get_client(settings).select_graph(graph_name)
    graph.query("MATCH (n) DETACH DELETE n")


def ping(settings: Settings | None = None) -> bool:
    """Health probe: can we talk to FalkorDB?"""
    try:
        run_query("RETURN 1", settings=settings)
        return True
    except Exception:  # pragma: no cover - health probe
        return False

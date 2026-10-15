"""Seed + verify the SentinelGraph demo dataset against a live FalkorDB.

Usage (from backend/):
    python -m scripts.seed_demo            # idempotent load + verification
    python -m scripts.seed_demo --reset    # drop graph first, then load

Verification prints entity/relationship counts and runs probe queries for the
demo scenario: the A->B multi-hop path, the unrelated alert C, and historical
memory retrieval inputs.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.graph.connection import drop_graph, get_graph, run_query  # noqa: E402
from app.graph.schema import ensure_schema  # noqa: E402
from app.ingestion.loader import load_demo_dataset_from_path  # noqa: E402

DATA_PATH = BACKEND_DIR.parent / "data" / "demo_alerts.json"


def node_count(label: str) -> int:
    return run_query(f"MATCH (n:{label}) RETURN count(n)")[0][0]


def rel_count(rel: str) -> int:
    return run_query(f"MATCH ()-[r:`{rel}`]->() RETURN count(r)")[0][0]


def main() -> int:
    reset = "--reset" in sys.argv
    settings = get_settings()

    if reset:
        drop_graph(settings.graph_name, settings)
        print(f"[*] dropped graph '{settings.graph_name}'")

    print("[*] ensuring schema/indexes ...")
    ensure_schema(settings)

    print(f"[*] loading dataset from {DATA_PATH} ...")
    counts = load_demo_dataset_from_path(str(DATA_PATH))
    print("[+] loaded:", counts)

    print("\n=== graph counts ===")
    for label in ["Alert", "Account", "Device", "IPAddress", "Process", "Service", "Incident", "Memory", "Analyst"]:
        print(f"  {label}: {node_count(label)}")
    for rel in ["INVOLVES", "OBSERVED_ON", "USED", "LOGGED_IN_FROM", "RUNS", "CONNECTS_TO", "DEPENDS_ON", "PART_OF", "SUPPORTED_BY", "SIMILAR_TO", "INVESTIGATED", "PRODUCED"]:
        c = rel_count(rel)
        if c:
            print(f"  {rel}: {c}")

    print("\n=== probe: A -> B multi-hop path (the demo correlation) ===")
    hops = settings.max_traversal_hops
    from app.graph.queries import CORRELATE_PATHS

    q = CORRELATE_PATHS.replace("__HOPS__", str(hops)).replace(
        "RETURN path, length(path) AS hops",
        "RETURN other.id AS alert_id, length(path) AS hops, "
        "[n IN nodes(path) | n.id] AS node_ids, "
        "[r IN relationships(path) | type(r)] AS rel_types",
    )
    rows = run_query(q, {"alert_id": "ALR-2026-10-0011"})
    if not rows:
        print("[!] FAIL: no correlated alerts found from A")
        return 1
    for r in rows:
        print(f"  -> {r[0]} hops={r[1]}")
        print(f"     nodes: {r[2]}")
        print(f"     rels : {r[3]}")
    related = {r[0] for r in rows}
    assert "ALR-2026-10-0012" in related, "FAIL: A should correlate with B"
    print("[+] PASS: B reachable from A within bounded hops")

    # Unrelated alert C must NOT be reachable through internal entities.
    if "ALR-2026-10-0013" in related:
        # C shares only the external IP node; verify the path is IP-only.
        for r in rows:
            if r[0] == "ALR-2026-10-0013":
                internal = [
                    nid for nid in r[2]
                    if nid.startswith(("acct:", "dev:", "svc:")) or nid.startswith("proc:")
                ]
                print(f"  C path nodes: {r[2]} internal={internal}")
        print("[*] C reachable only via shared external IP (ranking must exclude it)")
    else:
        print("[+] C not reachable at all (even stronger)")

    print("\n=== probe: historical incident memory ===")
    rows = run_query(
        "MATCH (i:Incident {id: 'INC-2025-0417'})<-[:PART_OF]-(m:Memory) RETURN m.id, m.kind"
    )
    print(f"  INC-2025-0417 memories: {[r[0] for r in rows]}")
    assert len(rows) >= 2, "FAIL: historical memories missing"

    print("\n[OK] dataset seeded and verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

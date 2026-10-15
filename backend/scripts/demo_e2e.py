"""SentinelGraph end-to-end demo (drives the live REST API).

Usage (from backend/, with uvicorn running on :8000 and FalkorDB up):
    python -m scripts.demo_e2e

Covers, in order:
  1. health / graph connectivity
  2. clean reseed of the synthetic dataset
  3. investigation of Alert A  -> groups B, excludes C + historical alert
  4. persistence: the result is re-fetched in a separate request
  5. graph neighborhood extraction
  6. analyst memory write + read-back across requests
  7. action workflow: propose -> approve -> reject, plus 409 on double-approve

Exit code 0 only when every check passes.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
ALERT_A = "ALR-2026-10-0011"
ALERT_B = "ALR-2026-10-0012"
ALERT_C = "ALR-2026-10-0013"
HISTORICAL = "ALR-2026-04-0091"

_results: list[tuple[bool, str]] = []


def call(method: str, path: str, payload: dict | None = None, expect: int = 200):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body}


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((ok, name))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" -- {detail}" if detail else ""))


def main() -> int:
    print("=" * 72)
    print("SentinelGraph end-to-end demo")
    print("=" * 72)

    # 1. Health -------------------------------------------------------------
    print("\n1) Backend + FalkorDB health")
    status, health = call("GET", "/health")
    check("GET /health -> 200", status == 200)
    check(
        "FalkorDB connected",
        health.get("falkordb") == "connected",
        f"status={health.get('status')} graph={health.get('graph')}",
    )

    # 2. Clean seed ---------------------------------------------------------
    print("\n2) Reseed synthetic dataset")
    status, seed = call("POST", "/demo/reset")
    check("POST /demo/reset -> 200", status == 200)
    check("3 demo alerts in graph", seed.get("alerts_in_graph") == 5,
          f"3 live + 2 historical stubs = {seed.get('alerts_in_graph')}")

    # 3. Investigate A ------------------------------------------------------
    print("\n3) Investigate Alert A (multi-hop correlation)")
    status, inv = call("POST", "/investigations",
                       {"alert_id": ALERT_A, "analyst": "demo.analyst"}, expect=201)
    check("POST /investigations -> 201", status == 201)
    if status != 201:
        print(json.dumps(inv, indent=2)[:800])
        return finish()

    related = inv.get("related_alert_ids", [])
    excluded = {e["alert_id"]: e for e in inv.get("excluded_alert_ids", [])}
    check("Alert B grouped with A", ALERT_B in related, f"related={related}")
    check("Alert C NOT grouped", ALERT_C not in related)
    check(
        "C exclusion cites external-IP reason",
        ALERT_C in excluded and "external" in excluded[ALERT_C]["reason"].lower(),
        excluded.get(ALERT_C, {}).get("reason", "")[:90] + "...",
    )
    check(
        "historical alert excluded as context",
        HISTORICAL in excluded and "historical" in excluded[HISTORICAL]["reason"].lower(),
    )

    path_ab = next(
        (
            e["path"]
            for e in inv.get("evidence", [])
            if e.get("path")
            and e["path"]["nodes"][0]["id"] == ALERT_A
            and e["path"]["nodes"][-1]["id"] == ALERT_B
        ),
        None,
    )
    check("real A->B graph path returned", path_ab is not None)
    if path_ab:
        chain = " -> ".join(n["id"] for n in path_ab["nodes"])
        rels = [e["type"] for e in path_ab["edges"]]
        ts_ok = any(e["props"].get("ts") for e in path_ab["edges"])
        check("path has >=3 nodes (genuine multi-hop)", len(path_ab["nodes"]) >= 3, chain)
        check("path edges carry timestamps", ts_ok, f"rels={rels}")

    check("observed facts separated from hypotheses",
          bool(inv.get("observed_facts")) and all(
              h["classification"] == "hypothesis" for h in inv.get("hypotheses", [])))
    check("uncertainty/missing evidence stated", bool(inv.get("missing_evidence")),
          "; ".join(inv.get("missing_evidence", []))[:110])
    check("historical memory retrieved",
          any(h["similar_incident_id"].startswith("INC-2025")
              for h in inv.get("historical_context", [])),
          ", ".join(h["similar_incident_id"] for h in inv.get("historical_context", [])))
    check("evidence-backed actions proposed (PROPOSED)",
          all(a["status"] == "PROPOSED" for a in inv.get("suggested_actions", []))
          and bool(inv.get("suggested_actions")),
          f"{len(inv.get('suggested_actions', []))} proposals")

    # 4. Persistence across a separate request ------------------------------
    print("\n4) Persistence (separate request reconstructs the run)")
    status, back = call("GET", f"/investigations/{inv['id']}")
    check("GET /investigations/{id} -> 200", status == 200)
    check("related alerts identical after reload",
          back.get("related_alert_ids") == inv.get("related_alert_ids"))
    check("evidence count identical after reload",
          len(back.get("evidence", [])) == len(inv.get("evidence", [])))

    # 5. Graph neighborhood -------------------------------------------------
    print("\n5) Graph neighborhood for the graph explorer")
    status, nb = call("GET", f"/graph/neighborhood/{ALERT_A}?hops=2")
    check("GET /graph/neighborhood -> 200", status == 200)
    node_ids = {n["id"] for n in nb.get("nodes", [])}
    check("seed + account present in neighborhood",
          ALERT_A in node_ids and "acct:ana.rios" in node_ids,
          f"{len(node_ids)} nodes, {len(nb.get('edges', []))} rels")
    check("edges reference returned nodes",
          all(e["src"] in node_ids and e["dst"] in node_ids for e in nb.get("edges", [])))

    # 6. Memory write + read-back ------------------------------------------
    print("\n6) Analyst memory (write, then read in a separate request)")
    incident_id = inv["incident_id"]
    status, mem = call("POST", "/memories", {
        "kind": "feedback",
        "content": "Demo: grouping A+B confirmed; payments host was the pivot.",
        "confidence": 0.9,
        "incident_id": incident_id,
        "created_by": "demo.analyst",
    }, expect=201)
    check("POST /memories -> 201", status == 201)
    status, mems = call("GET", f"/memories?incident_id={incident_id}")
    stored_ids = {m["id"] for m in mems.get("memories", [])}
    check("memory readable in a later request",
          status == 200 and mem.get("id") in stored_ids)

    # 7. Action workflow ----------------------------------------------------
    print("\n7) Simulated action workflow with approval gate")
    action = inv["suggested_actions"][0]
    action_id = action["id"]
    check("proposal starts PROPOSED", action["status"] == "PROPOSED",
          f"{action['action_type']} -> {action['target_id']}")

    status, approved = call("POST", f"/actions/{action_id}/approve",
                            {"analyst": "demo.analyst", "reason": "evidence reviewed"})
    check("approve -> APPROVED", status == 200 and approved.get("status") == "APPROVED")

    status, _ = call("POST", f"/actions/{action_id}/approve", {"analyst": "demo.analyst"})
    check("double-approve -> 409 conflict", status == 409, f"got {status}")

    second = inv["suggested_actions"][1]
    status, rejected = call("POST", f"/actions/{second['id']}/reject",
                            {"analyst": "demo.analyst", "reason": "too aggressive"})
    check("reject -> REJECTED", status == 200 and rejected.get("status") == "REJECTED")

    status, _ = call("POST", "/actions/act:does-not-exist/approve", {"analyst": "x"})
    check("unknown action -> 404", status == 404, f"got {status}")

    status, _ = call("POST", "/investigations", {"alert_id": "ALR-NOPE"})
    check("unknown alert -> 404", status == 404, f"got {status}")

    return finish()


def finish() -> int:
    passed = sum(1 for ok, _ in _results if ok)
    total = len(_results)
    print("\n" + "=" * 72)
    print(f"RESULT: {passed}/{total} checks passed")
    print("=" * 72)
    return 0 if passed == total and total > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""API contract tests over the required endpoints (FastAPI TestClient).

Each check uses separate HTTP requests -- the same boundary the demo UI
exercises -- so persistence claims are proven across request boundaries.
"""

from __future__ import annotations

from tests.conftest import ALERT_A, ALERT_B, ALERT_C


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["falkordb"] == "connected"
    assert body["counts"].get("alert", 0) >= 3


def test_post_alert_is_idempotent(client):
    import uuid

    alert_id = f"ALR-TEST-IDEMP-{uuid.uuid4().hex[:10]}"
    payload = {
        "alert_id": alert_id,
        "title": "Test alert for idempotent ingestion",
        "severity": "medium",
        "alert_type": "test",
        "timestamp": "2026-10-13T10:00:00Z",
        "source": "pytest",
        "account": "acct:ana.rios",
    }
    r1 = client.post("/alerts", json=payload)
    assert r1.status_code == 201, r1.text
    assert r1.json()["created"] is True

    r2 = client.post("/alerts", json=payload)
    assert r2.status_code == 201
    assert r2.json()["created"] is False, "same alert_id must not duplicate nodes"
    assert r1.json()["alert_id"] == r2.json()["alert_id"]


def test_post_alerts_ingest_bulk(client):
    import uuid

    suffix = uuid.uuid4().hex[:10]
    payload = {
        "alerts": [
            {
                "alert_id": f"ALR-TEST-BULK-1-{suffix}",
                "title": "Bulk ingest test alert one",
                "severity": "low",
                "alert_type": "test",
                "timestamp": "2026-10-13T10:05:00Z",
                "source": "pytest",
            },
            {
                "alert_id": f"ALR-TEST-BULK-2-{suffix}",
                "title": "Bulk ingest test alert two",
                "severity": "low",
                "alert_type": "test",
                "timestamp": "2026-10-13T10:06:00Z",
                "source": "pytest",
                "device": "dev:fin-ws-1042",
            },
        ]
    }
    r = client.post("/alerts/ingest", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["accepted"] == 2
    assert body["created"] == 2 and body["updated"] == 0
    # Idempotent: ingesting again updates rather than duplicating.
    r2 = client.post("/alerts/ingest", json=payload)
    assert r2.status_code == 201
    assert r2.json()["created"] == 0 and r2.json()["updated"] == 2


def test_alert_validation_rejects_bad_input(client):
    r = client.post("/alerts", json={"alert_id": "x", "title": "bad"})
    assert r.status_code == 422


def test_create_and_fetch_investigation_across_requests(client):
    r = client.post("/investigations", json={"alert_id": ALERT_A, "analyst": "tester"})
    assert r.status_code == 201, r.text
    res = r.json()

    assert res["related_alert_ids"] == [ALERT_B]
    assert ALERT_C not in res["related_alert_ids"]
    assert res["hypotheses"] and res["observed_facts"]
    assert res["missing_evidence"]

    # Fetch in a separate request: reconstructed from FalkorDB, not memory.
    r2 = client.get(f"/investigations/{res['id']}")
    assert r2.status_code == 200
    back = r2.json()
    assert back["related_alert_ids"] == res["related_alert_ids"]
    assert len(back["evidence"]) == len(res["evidence"])

    # 404 for unknown ids.
    assert client.get("/investigations/inv:nope").status_code == 404


def test_investigation_unknown_alert_is_404(client):
    r = client.post("/investigations", json={"alert_id": "ALR-DOES-NOT-EXIST"})
    assert r.status_code == 404


def test_graph_neighborhood(client):
    r = client.get(f"/graph/neighborhood/{ALERT_A}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["center_id"] == ALERT_A
    node_ids = {n["id"] for n in body["nodes"]}
    assert ALERT_A in node_ids
    assert "acct:ana.rios" in node_ids
    assert body["edges"], "neighborhood must include relationships"
    # Edges reference real returned nodes.
    for e in body["edges"]:
        assert e["src"] in node_ids and e["dst"] in node_ids


def test_graph_neighborhood_unknown_node_404(client):
    assert client.get("/graph/neighborhood/no:such:node").status_code == 404


def test_memories_endpoints(client):
    payload = {
        "kind": "finding",
        "content": "API test finding: payments host was the pivot device.",
        "confidence": 0.7,
        "incident_id": "INC-2025-0417",
        "created_by": "tester",
    }
    r = client.post("/memories", json=payload)
    assert r.status_code == 201, r.text
    mem = r.json()
    assert mem["id"] and mem["kind"] == "finding"

    r2 = client.get("/memories", params={"incident_id": "INC-2025-0417"})
    assert r2.status_code == 200
    ids = {m["id"] for m in r2.json()["memories"]} if isinstance(r2.json(), dict) else {m["id"] for m in r2.json()}
    assert mem["id"] in ids, "memory must be readable in a later request"


def test_action_lifecycle_over_http(client):
    inv = client.post("/investigations", json={"alert_id": ALERT_A, "analyst": "tester"}).json()
    assert inv["suggested_actions"], "investigation should propose actions"
    assert {a["status"] for a in inv["suggested_actions"]} <= {
        "PROPOSED", "APPROVED", "REJECTED", "COMPLETED"
    }

    def _create(target: str) -> dict:
        r = client.post(
            "/actions",
            json={
                "incident_id": inv["incident_id"],
                "action_type": "REVIEW_DEVICE",
                "target_id": target,
                "description": f"Simulated lifecycle test action for {target}.",
                "created_by": "tester",
            },
        )
        assert r.status_code == 201, r.text
        return r.json()

    # Fresh proposal -> explicit approval.
    action = _create("dev:srv-payments-01")
    assert action["status"] == "PROPOSED"
    r = client.post(
        f"/actions/{action['id']}/approve",
        json={"analyst": "tester", "reason": "reviewed evidence"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "APPROVED"

    # Approving again is a conflict, not a silent repeat.
    r2 = client.post(f"/actions/{action['id']}/approve", json={"analyst": "tester"})
    assert r2.status_code == 409

    # A separate proposal can be rejected.
    other = _create("dev:fin-ws-1042")
    r3 = client.post(
        f"/actions/{other['id']}/reject",
        json={"analyst": "tester", "reason": "too aggressive for now"},
    )
    assert r3.status_code == 200
    assert r3.json()["status"] == "REJECTED"

    # Unknown action -> 404.
    assert client.post("/actions/act:nope/approve", json={"analyst": "t"}).status_code == 404


def test_action_create_endpoint_requires_existing_incident(client):
    r = client.post(
        "/actions",
        json={
            "incident_id": "INC-DOES-NOT-EXIST",
            "action_type": "BLOCK_IP",
            "target_id": "ip:203.0.113.44",
            "description": "Simulated block attempt against a missing incident.",
        },
    )
    assert r.status_code == 404

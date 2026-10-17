# SentinelGraph — 3-minute demo script

Record the browser at 1080p with the dashboard on `http://localhost:3000`
(production build) and, optionally, a terminal window beside it. Every step
below corresponds to behaviour that was verified on the running system —
quoted values are from those verified runs.

## Prep (before recording)

```bash
docker compose up -d                     # FalkorDB on 6379/7379
cd backend  && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd frontend && npm run build && npm run start -- --port 3000
curl -X POST http://127.0.0.1:8000/demo/reset   # pristine demo graph
```

Expected: `/health` returns `{"status":"ok","falkordb":"connected",...}`;
the dashboard header shows the green pill **ok · connected · sentinelgraph**.

---

## 0:00–0:20 — The problem in one sentence

Camera on the dashboard queue. Say: *"Three unrelated-looking alerts. A
conventional triage treats them independently. SentinelGraph uses FalkorDB
to connect them — or prove they shouldn't be connected."*

Point at the queue: 3 alerts with severity filters — `ALR-2026-10-0011`
(high, suspicious sign-in), `ALR-2026-10-0012` (critical, C2 beacon on the
payments server), `ALR-2026-10-0013` (high, malware on a marketing laptop).

## 0:20–0:50 — Graph-first context

Click **ALR-2026-10-0011**. The graph explorer loads its live 2-hop
neighborhood from FalkorDB (~22 nodes, ~32 relationships, ~7 activity edges).
Highlight: solid blue edges are observed activity (`LOGGED_IN_FROM · 09:12`,
`CONNECTS_TO · 09:28`), dashed are inventory (`USED`). Click
`dev:fin-ws-1042` to re-center the traversal — the query is a live,
parameterized Cypher BFS.

## 0:50–1:40 — The investigation

Click **Run investigation**. Walk the result:

- **Grouped:** `ALR-2026-10-0012` only. Read the evidence path verbatim:
  `ALR-2026-10-0011 -[OBSERVED_ON @ 09:14]-> dev:fin-ws-1042
  -[CONNECTS_TO @ 09:28]-> dev:srv-payments-01 -[INVOLVES @ 09:43]-> ALR-2026-10-0012`
  — "every hop is a real retrieved relationship with a timestamp and a
  source alert id".
- **Hypothesis, labeled as such:** 76% confidence; expand
  *"why this score (transparent criteria)"* to show the breakdown
  (entity 3.0 = internal bridge, temporal 2.0, activity 1.0, hop −0.5).
- **Observed facts panel:** literal edges from the graph, kept separate
  from the inference.

## 1:40–2:05 — What it refused to group

Scroll to **Evaluated and excluded candidates**:

- `ALR-2026-10-0013` — score 2.5, excluded: *"Every retrieved path into this
  alert crosses through non-discriminative external IP address(es)
  ['ip:203.0.113.44'] … Sharing a public IP (or a severity level) never
  justifies grouping."*
- `ALR-2026-04-0091` — historical archive alert: context only, never grouped.
- Open **uncertainty**: *"Flow dev:fin-ws-1042 → dev:srv-payments-01 (port
  8443) has no process attribution in the graph."*

## 2:05–2:30 — Persistent memory

Show **Related incidents & historical memory**: `INC-2025-0417`
("Ransomware staging via finance workstation") recalled through a
`SIMILAR_TO` edge with its basis (*shared entities, weighted Jaccard*), its
stored findings, and the trust note *"Treat as an unverified lead, not
confirmed truth."* Then the **Timeline** tab: chronological events built
only from retrieved timestamps.

Re-run the investigation on the same alert — it merges into the same
incident with the evidence and actions already stored in the graph,
reconstructed from FalkorDB, not server memory. (API equivalent:
`GET /investigations/{id}` returns the full stored result even after a
backend restart.)

## 2:30–2:55 — Acting, with an approval gate

In **Recommended actions (simulated)**: press **Approve** on
`BLOCK_IP ip:203.0.113.44` → status flips to **APPROVED** with
"decided by demo.analyst" and the recorded reason. Press **Reject** on a
`REVIEW_DEVICE` → **REJECTED**. Then store a short analyst note in
**Incident memory** and show it re-appearing (persisted in FalkorDB).
Say: *"Nothing here touches a real firewall or EDR — a proposal cannot
change state without an explicit analyst decision."*

## 2:55–3:00 — Close on the receipts

Terminal (optional but strong):

```bash
cd backend  && python -m pytest tests/ -q    # 33 passed
cd frontend && npm test                      # 12 passed
cd backend  && python -m scripts.demo_e2e    # 30/30 checks passed
```

Close with: *"Everything you saw is synthetic data in FalkorDB; the graph
is the retrieval, the evidence store, the memory and the workflow state."*

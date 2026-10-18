# SentinelGraph

**Graph-powered cybersecurity incident investigation agent** — Graph Hacks 2026, powered by FalkorDB.

SentinelGraph treats security alerts as a *connected* problem. When an analyst
investigates an alert, the agent traverses **FalkorDB** with bounded multi-hop
queries to find neighbouring alerts, assembles the *actual* graph paths as
evidence, ranks candidates with transparent criteria, retrieves similar
historical incidents from persistent graph memory, and proposes simulated
response actions that require explicit analyst approval.

The graph is the reasoning and memory layer — not a visualization bolted onto
a chatbot:

- **Retrieval = Cypher.** Every fact shown in the UI comes from a parameterized
  FalkorDB query. Nothing is invented client-side or by an LLM.
- **Evidence = paths.** Hypotheses cite concrete node/relationship chains with
  timestamps and source alert IDs.
- **Memory = graph.** Findings, analyst feedback, incidents and their
  similarity links live in the same graph and survive restarts.
- **Acting = workflow over graph state.** Actions are `Action` nodes gated by
  a status machine; nothing is executed against real systems.

**Tracks:** *Agents That Act on Connected Data* (primary),
*Agent Memory and Coordination* (secondary).

---

## Demo scenario (deterministic, fully synthetic)

| Alert | What it is | Outcome |
|---|---|---|
| **A** `ALR-2026-10-0011` | Suspicious sign-in of `ana.rios` from an unrecognised external IP (seed) | investigated |
| **B** `ALR-2026-10-0012` | C2 beacon candidates: payments server contacting a foreign IP | **grouped** with A via a 3-hop path |
| **C** `ALR-2026-10-0013` | Malware on marketing laptop | **excluded** — shares only an external IP |
| `ALR-2026-04-0091` | Archived historical alert | context only (`historical=true` hard rule) |

The grouped path (retrieved from FalkorDB, not hardcoded):

```
ALR-2026-10-0011 -[OBSERVED_ON @ 09:14]-> dev:fin-ws-1042
                 -[CONNECTS_TO @ 09:28]-> dev:srv-payments-01
                 -[INVOLVES  @ 09:43]-> ALR-2026-10-0012
```

Historical incidents `INC-2025-0417` / `INC-2025-0512` are linked through
`SIMILAR_TO` and their stored findings are recalled with provenance and an
explicit "unverified lead" trust note.

---

## Quick start (Windows-friendly)

### 1. FalkorDB

```bash
docker compose up -d          # starts falkordb on 6379 (HTTP on 7379)
# or, without compose:
docker run -d --name falkordb -p 6379:6379 -p 7379:7379 falkordb/falkordb:latest
```

### 2. Backend (FastAPI)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows (Git Bash: .venv/Scripts/python.exe)
pip install -r backend/requirements.txt
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The demo dataset is auto-seeded on startup when the graph is empty
(`AUTO_SEED_ON_STARTUP=true`). Reset any time with `POST /demo/reset`.

### 3. Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev                   # http://localhost:3000 (landing page)
# production: npm run build && npm run start -- --port 3000
```

Open `http://localhost:3000` for the landing page; the investigation
workspace is at `http://localhost:3000/app`. The frontend calls the backend
at `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`; CORS allows
`localhost:3000`).

### 4. Verify

```bash
cd backend && python -m pytest tests/ -q     # 33 tests, live FalkorDB
cd frontend && npm test                      # 19 vitest tests (client + UI)
cd frontend && npm run lint && npm run build
python -m scripts.demo_e2e                   # from backend/ — full API demo
```

---

## Live demo

| Service | URL |
|---|---|
| Frontend | https://frontend-production-717c.up.railway.app |
| Backend API | https://backend-production-f51e.up.railway.app |
| FalkorDB | private service (volume-backed, not exposed publicly) |

Hosted on Railway: three services in one project — FalkorDB (Docker image +
500 MB persistent volume mounted at `/data`), the FastAPI backend, and the
Next.js frontend. All services build from the Dockerfiles in this repository
(`backend/Dockerfile`, `frontend/Dockerfile`).

Infrastructure is defined as code in `.railway/railway.ts` (services, builder,
volume). Variable names (values are set in Railway, never committed):
`FALKORDB_HOST`, `FALKORDB_PORT`, `CORS_ORIGINS`, `NEXT_PUBLIC_API_URL`,
`AUTO_SEED_ON_STARTUP`. Backend and FalkorDB talk over Railway's private
network; only the frontend and backend have public domains.

---

## Architecture

```
frontend/   Next.js 16 · React 19 · TypeScript · Tailwind v4 · @xyflow/react
   │  REST (JSON)
backend/    FastAPI · Pydantic validation · provider-optional LLM summarizer
   │  official falkordb Python client, parameterized Cypher only
FalkorDB    graph = facts + evidence + memory + workflow state
```

| Backend module | Responsibility |
|---|---|
| `app/graph/connection.py` | client pool, `run_query`, safe `drop_graph` |
| `app/graph/schema.py` | labels, relationship docs, indexes (`ensure_schema`) |
| `app/graph/queries.py` | every shared parameterized Cypher statement |
| `app/ingestion/` | validation/normalization, idempotent upserts, seed loader |
| `app/investigation/engine.py` | the pipeline: traverse → extract → group → persist |
| `app/investigation/ranking.py` | transparent scoring (documented below) |
| `app/memory.py` | incident findings, feedback, `SIMILAR_TO` similarity |
| `app/action_workflow.py` | `PROPOSED → APPROVED/REJECTED → COMPLETED` gating |
| `app/llm.py` | optional summarizer; **never** touches retrieval or evidence |
| `app/routes/` | thin HTTP layer over the modules above |

### Investigation pipeline

1. **Seed context** — `GET` the alert's `INVOLVES`/`OBSERVED_ON` neighbors.
2. **Bounded traversal** — `CORRELATE_PATHS` walks `*2..max_hops` through
   telemetry relationships only; intermediate nodes must be entities (no
   other `Alert`, no meta nodes) so grouping can never be self-referential.
3. **Rank + group/exclude** — every candidate gets a score breakdown and,
   if excluded, a human-readable reason.
4. **Evidence** — best path per grouped alert is stored as an immutable
   `Evidence` node (JSON snapshot) linked `SUPPORTED_BY` from the incident.
5. **Observed vs inferred** — facts are literal retrieved edges; hypotheses
   are classified `hypothesis` with confidence derived from the score and
   their `missing_evidence` list.
6. **Memory** — a `finding` is stored for the incident; `SIMILAR_TO` edges to
   historical incidents are computed (weighted Jaccard over incident entity
   sets) and their memories recalled with provenance + trust note.
7. **Actions** — deterministic `PROPOSED` actions from evidence (accounts,
   devices, external IPs on retrieved paths).
8. **Persist** — the full result is reconstructible from graph artifacts
   (`GET /investigations/{id}` rebuilds it without any server-side cache).

### Ranking (transparent, documented criteria)

```
total = entity_score + temporal_score + corroboration_score + hop_penalty
group iff total >= CORRELATION_THRESHOLD (3.0) AND entity_score > 0
```

- **shared entities** (2-hop, both alerts touch it): Account 4.0, Device 3.0,
  Process 2.5, Service 2.0, internal IP 1.0.
- **critical bridge**: an edge crossing from *the seed's own entities* to
  *the candidate's own entities* contributes `min(weight)` for observed
  activity (`LOGGED_IN_FROM`/`RUNS`/`CONNECTS_TO`), half for inventory edges.
  A crossing through an **external IP scores 0** — sharing a public IP is
  never a correlation.
- **temporal**: `|Δt|` ≤1h +2.0, ≤6h +1.5, ≤24h +1.0, ≤7d +0.5.
- **corroboration**: +1.0 if the path contains observed-activity edges.
- **hop penalty**: −0.5 per hop beyond 2.
- **scores zero by policy**: equal severity, shared public IP, shared tags/source.
- **hard rule**: `historical=true` alerts are context, never grouped.

### Memory & trust policy

- `Memory` nodes carry `kind` (`finding`|`feedback`), `confidence`,
  `created_by`, `created_at` and the originating `investigation_id`.
- Recalled historical memories always ship with a trust note:
  *"Historical context from a previous investigation. Treat as an unverified
  lead, not confirmed truth for the current incident."*
- Current-run hypotheses stay classified as hypotheses regardless of memory.

### Action workflow (all simulated)

```
PROPOSED ──approve──> APPROVED ──complete──> COMPLETED
    └─────reject─────> REJECTED        (terminal)
```

Invalid transitions return **409**, unknown ids **404**. Every action node
records `APPROVED_BY` with analyst, reason and timestamp. No real system is
ever contacted.

---

## Graph schema

**Nodes:** `Alert` `Account` `Device` `IPAddress` `Process` `Service`
`Incident` `Evidence` `Memory` `Action` `Analyst` `Investigation`

| Relationship | Meaning | Key props |
|---|---|---|
| `INVOLVES` | Alert → entity it references | `ts`, `alert_id`, `role` |
| `OBSERVED_ON` | Alert → device telemetry originated from | `ts`, `alert_id` |
| `REFERENCES_IP` | Alert → IP involved by reference | `ts`, `alert_id` |
| `LOGGED_IN_FROM` | Account → IP (auth event) | `ts`, `success`, `source` |
| `USED` | Account → Device inventory association | `first_seen`, `last_seen` |
| `RUNS` | Process → Device (execution) | `ts` |
| `CONNECTS_TO` | Device → Device/IP flow | `ts`, `port`, `proto` |
| `DEPENDS_ON` | Service → Service | — |
| `PART_OF` | Alert/Memory → Incident | `grouped_at`, `investigation_id` |
| `SUPPORTED_BY` | Incident → Evidence | `added_at` |
| `SIMILAR_TO` | Incident → Incident | `score`, `basis` |
| `INVESTIGATED` | Incident → Analyst | — |
| `PRODUCED` | Investigation → Evidence | `ts` |
| `PROPOSED_FOR` | Action → Incident | `created_by` |
| `APPROVED_BY` | Action → Analyst | `decision`, `reason`, `decided_at` |

Timestamps are normalized to UTC ISO-8601 (`Z`); every edge that originates
from an alert carries `ts` + `alert_id` for provenance.

### Sample Cypher (verbatim from `app/graph/queries.py`)

Bounded multi-hop correlation (the core traversal):

```cypher
MATCH path = (seed:Alert {id: $alert_id})-[rs*2..4]-(other:Alert)
WHERE other.id <> $alert_id
  AND ALL(r IN relationships(path) WHERE type(r) IN ['INVOLVES','OBSERVED_ON',...])
  AND ALL(i IN range(1, size(nodes(path))-2)
      WHERE NOT (nodes(path)[i]:Alert OR nodes(path)[i]:Incident
              OR nodes(path)[i]:Memory OR nodes(path)[i]:Evidence
              OR nodes(path)[i]:Action OR nodes(path)[i]:Investigation))
RETURN path, length(path) AS hops
LIMIT 200
```

Historical similarity retrieval:

```cypher
MATCH (inc:Incident {id: $incident_id})-[s:SIMILAR_TO]->(old:Incident)
WHERE s.score >= $min_score
RETURN old.id, properties(old), s.score, s.basis
ORDER BY s.score DESC
```

Upsert (idempotent, no user input ever interpolated):

```cypher
MERGE (n:`Alert` {id: $id})
SET n += $props
RETURN n.id AS id
```

---

## API reference

| Method & path | Purpose |
|---|---|
| `GET /health` | liveness, FalkorDB status, graph counts |
| `POST /alerts` | ingest one validated alert (idempotent; `created` flag) |
| `POST /alerts/ingest` | bulk ingest (`accepted/created/updated`) |
| `GET /alerts` | queue with `severity`, `ungrouped_only` filters |
| `GET /alerts/{id}` | alert + linked entities with edge provenance |
| `POST /investigations` | run the investigation pipeline for an alert |
| `GET /investigations/{id}` | reconstruct a persisted run from graph artifacts |
| `GET /investigations` | list past runs |
| `GET /graph/neighborhood/{id}` | BFS neighborhood (1–4 hops) for the explorer |
| `GET /graph/schema` | schema documentation as served by the API |
| `POST /memories` | persist finding/feedback with provenance |
| `GET /memories?incident_id=` | list stored memories |
| `GET /actions?incident_id=` | list action proposals |
| `POST /actions` | create a `PROPOSED` action |
| `POST /actions/{id}/approve` | explicit analyst approval |
| `POST /actions/{id}/reject` | explicit analyst rejection |
| `POST /actions/{id}/complete` | mark an approved simulated action done |
| `GET /incidents`, `GET /incidents/{id}` | incident detail incl. memory/evidence |
| `POST /demo/reset` | drop + reseed the synthetic dataset |

All request/response models are Pydantic-validated (422 on invalid input).

---

## Optional LLM

Set `LLM_PROVIDER` + `LLM_API_KEY` (see `.env.example`) to have the
`summary` field written by a model. Without a key the pipeline uses a local
deterministic summarizer — **the core investigation never depends on it**,
and the LLM never performs retrieval or may add evidence.

---

## Verified results

See [VERIFIED_RESULTS.md](VERIFIED_RESULTS.md) for the exact commands and
outputs produced during development (backend tests, frontend checks, live
end-to-end demo).

## AI coding assistant disclosure

This project was built with the assistance of an AI coding assistant
(Codebuff / Google Antigravity) in accordance with the Graph Hacks 2026
AI policy. All graph schema design, Cypher query logic, investigation
ranking criteria, and test cases were authored and reviewed by the
submitter. AI assistance was used for boilerplate, documentation
formatting, and iteration speed. This is disclosed on the submission form.

## Limitations

- The demo dataset is small and synthetic; ranking thresholds are tuned for it
  and would need recalibration on real telemetry volumes.
- Path enumeration is capped (`LIMIT 200`, ≤4 hops) to stay predictable —
  very dense graphs need cardinality-aware sampling instead.
- `SIMILAR_TO` uses weighted Jaccard over incident entity sets; embeddings
  would generalise better on large histories.
- The LLM summarizer is single-shot (no streaming/tool-calling agents) by
  design, so judges can audit every claim against graph evidence.
- All response actions are simulated; integrating real SOAR/EDR playbooks is
  intentionally out of scope.

## Repository layout

```
sentinelgraph/
├── backend/
│   ├── app/            # FastAPI app (graph, ingestion, investigation, routes)
│   ├── scripts/        # seed + demo_e2e
│   └── tests/          # 33 pytest tests against live FalkorDB
├── frontend/           # Next.js dashboard
├── data/demo_alerts.json
├── docker-compose.yml
├── .env.example
└── README.md
```

**Data safety:** every account, device, IP, process and alert in
`data/demo_alerts.json` is fabricated (documentation IP ranges, dummy hashes).
No real credentials, logs or customer data are used anywhere.

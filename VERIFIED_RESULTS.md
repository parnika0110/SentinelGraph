# Verified results

Environment: Windows (Git Bash), Python 3.14, Node 24, Docker Desktop with
`falkordb/falkordb` on `6379`/`7379`, Next.js 16.4.1 (production build),
FastAPI via uvicorn on `127.0.0.1:8000`.

Every command below was actually executed against this workspace.

---

## 1. Backend test suite

```bash
cd backend && python -m pytest tests/ -q
```

```
33 passed, 1 warning in 2.48s
```

Run twice back-to-back to prove the suite (and ingestion) is idempotent —
both runs green. Coverage:

- **Connected case** — `ALR-2026-10-0011` groups `ALR-2026-10-0012` with a
  real retrieved path; edges are chain-consistent, carry timestamps and
  source alert IDs; hypotheses cite existing evidence ids.
- **Unrelated case** — `ALR-2026-10-0013` is excluded with an
  external-IP reason (`entity_score <= 0` asserted); historical alert
  excluded by the `historical=true` hard rule; investigating C itself
  groups nothing.
- **Missing evidence** — telemetry gaps reported and attached to hypotheses.
- **Persistence** — `get_investigation()` reconstructs an identical result
  (related alerts, evidence, incident, hypothesis ids) in a separate call.
- **Memory** — feedback written through one call is readable through another;
  historical memories always carry provenance and the trust caveat.
- **Actions** — `PROPOSED → APPROVED → COMPLETED` gating, rejection path,
  409 on invalid transitions, 404 on unknown ids, evidence-backed proposals.
- **API contract** — all required endpoints via `TestClient`, including
  idempotent `POST /alerts` (`created=true` then `false`) and bulk ingest
  (`created=2` then `updated=2`).

## 2. Frontend checks

```bash
cd frontend
npm run lint        # eslint -> 0 errors, 0 warnings
npx tsc --noEmit    # clean
npm run build       # Next.js 16.4.1 compiled successfully, "/" static route
```

Production server started with `npm run start -- --port 3000` and verified in
a real browser.

## 3. Live end-to-end demo (REST API)

```bash
cd backend && python -m scripts.demo_e2e
```

```
RESULT: 30/30 checks passed
```

Highlights of the 30 checks:

- `GET /health` → `status=ok`, `falkordb=connected`, graph `sentinelgraph`
- `POST /demo/reset` → 5 alerts (3 live + 2 historical stubs)
- `POST /investigations` → 201; **B grouped**, **C excluded**
  ("...crosses through non-discriminative external IP address(es)..."),
  historical alert excluded as context
- Real path returned:
  `ALR-2026-10-0011 -> dev:fin-ws-1042 -> dev:srv-payments-01 -> ALR-2026-10-0012`
  with rels `['OBSERVED_ON', 'CONNECTS_TO', 'INVOLVES']` and timestamps
- Observed facts vs hypotheses separated; missing-evidence gap stated
  (unattributed port-8443 flow); historical incident `INC-2025-0417` recalled
- 6 evidence-backed actions proposed as `PROPOSED`
- Persistence: `GET /investigations/{id}` in a separate request returns the
  same related alerts and evidence count
- Neighborhood: 22 nodes / 32 relationships, all edges endpoint-consistent
- Memory: POST then GET in separate requests round-trips the id
- Workflow: approve → `APPROVED`, double-approve → **409**, reject →
  `REJECTED`, unknown action → **404**, unknown alert → **404**

## 4. Browser walkthrough (production build)

- Health pill: `ok · connected · sentinelgraph`
- Queue: 3 alerts with severity + `new`/`grouped` status, filters work
- Selecting Alert A loads its 2-hop neighborhood (22 nodes, 32 rels, 7
  activity edges; edge labels show type + time)
- **Run investigation** → result panel: grouped `ALR-2026-10-0012`,
  excluded 2, gaps 1, hypothesis at 76% confidence with expandable score
  breakdown, evidence path rendered node-by-node with `-[REL @ ts]->`
- **Historical panel**: `INC-2025-0417` similarity + stored findings with
  "unverified lead" trust notes
- **Actions**: APPROVE on `BLOCK_IP` → `APPROVED` (decided by
  `demo.analyst`, reason recorded); REJECT on a `REVIEW_DEVICE` → `REJECTED`
- **Memory**: analyst feedback stored via the panel and read back from
  FalkorDB (`confidence 70%`)
- Browser console: **0 errors**; all API calls 200/201

## 5. Known environment quirks (worked around, not product issues)

- `next dev` HMR WebSocket does not survive the preview proxy
  (`ERR_INVALID_HTTP_RESPONSE`), which prevented hydration *in the preview
  tool* — the production build (`next start`) hydrates and runs normally and
  is what the walkthrough above used.
- Python 3.14 `ipaddress.is_private` returns `True` for TEST-NET ranges, which
  initially misclassified the external attacker IP as internal; `ip_scope()`
  now classifies by explicit RFC1918/loopback/link-local/ULA ranges.

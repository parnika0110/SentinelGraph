# SentinelGraph — Hackathon Submission

**Event:** Graph Hacks: Context for AI Agents — powered by FalkorDB
(organizer: WeMakeDevs)
**Tracks entered:** *Agents That Act on Connected Data* (primary),
*Agent Memory and Coordination* (secondary)

> Repository URL: _\<to be filled after the public repo is created\>_
> Demo video: _\<to be filled after recording\>_ (follow [DEMO_SCRIPT.md](DEMO_SCRIPT.md))

---

## Project description (submission form text)

SentinelGraph investigates security alerts as a **connected** problem.
Analysts do not triage alerts one by one: when an alert is investigated, the
agent runs **bounded multi-hop traversals in FalkorDB** to find neighbouring
alerts, turns the *actual retrieved graph paths* into evidence, ranks
candidates with fully transparent criteria, recalls similar historical
incidents from persistent graph memory, and proposes simulated response
actions that cannot change state without explicit analyst approval.

**FalkorDB is the reasoning and memory layer, not a display store:**

- **Multi-hop alert correlation.** A parameterized Cypher query walks
  telemetry relationships (`INVOLVES`, `OBSERVED_ON`, `LOGGED_IN_FROM`,
  `RUNS`, `CONNECTS_TO`, `USED`, …) up to 4 hops, forbidding traversal
  through meta nodes so grouping can never be self-referential. In the demo,
  a suspicious login (`ALR-2026-10-0011`) is linked to a C2-beacon alert on
  the payments server (`ALR-2026-10-0012`) through the retrieved path
  `workstation -[CONNECTS_TO]-> server`, while an alert sharing only an
  external IP is **explicitly excluded** with a human-readable reason
  ("sharing a public IP never justifies grouping"). Equal severity, shared
  tags and shared public IPs score zero by policy.
- **Evidence-path explanations.** Every hypothesis cites the concrete
  nodes, relationships and timestamps retrieved from the graph plus the
  source alert IDs; observed facts and inferred hypotheses are strictly
  separated, every score is exposed as a breakdown, and telemetry gaps are
  reported as stated uncertainty instead of being smoothed over.
- **Persistent incident memory.** Findings, analyst feedback, incidents and
  their weighted-Jaccard `SIMILAR_TO` links live in the same graph and
  survive restarts and separate API requests. Recalled historical findings
  always carry provenance (author, timestamp, source incident) and an
  explicit "unverified lead, not confirmed truth" trust note.
- **Agents that act — safely.** Evidence-backed actions (`BLOCK_IP`,
  `ISOLATE_DEVICE`, `DISABLE_ACCOUNT`, …) are graph nodes with a status
  machine `PROPOSED → APPROVED/REJECTED → COMPLETED`; approval is an
  explicit, recorded analyst decision (`APPROVED_BY` with reason and
  timestamp), invalid transitions return 409, and every action is simulated —
  no real system is ever contacted.

The web dashboard shows the incident queue, the investigation result
(facts vs hypotheses, uncertainty, excluded candidates), an interactive
FalkorDB graph explorer, the evidence timeline, historical memory, and the
action approval controls — all rendered from live API responses with zero
hardcoded results.

**Compliance:** 100% synthetic data (fabricated accounts, documentation IP
ranges, dummy hashes — no real credentials/logs); all response actions are
simulated; README documents setup, the full graph data model and the
verbatim Cypher the product depends on; complete local setup instructions
are provided (no live deployment). Built with an AI coding assistant
(Codebuff) in accordance with the event's AI policy — to be disclosed on the
submission form.

## Verified results (from verified runs — see [VERIFIED_RESULTS.md](VERIFIED_RESULTS.md))

| Check | Result |
|---|---|
| Backend pytest (live FalkorDB) | **33 passed**, idempotent across back-to-back runs |
| Frontend vitest (jsdom) | **12 passed** |
| Frontend lint / typecheck / production build | clean / clean / success |
| End-to-end API demo (`python -m scripts.demo_e2e`) | **30/30 checks passed** |
| Browser walkthrough (production build) | investigation, graph explorer, approve/reject, memory write+readback, 0 console errors |

## What a judge should look at

- [README.md](README.md) — architecture, graph schema, ranking rules, verbatim Cypher, API reference
- [backend/app/graph/queries.py](backend/app/graph/queries.py) — every parameterized Cypher statement
- [backend/app/investigation/ranking.py](backend/app/investigation/ranking.py) — the transparent, documented scoring
- [backend/tests/](backend/tests) — connected / unrelated / missing-evidence / persistence / approval-gate tests
- [data/demo_alerts.json](data/demo_alerts.json) — the deterministic synthetic dataset

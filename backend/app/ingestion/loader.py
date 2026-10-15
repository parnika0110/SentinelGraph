"""Ingestion service: idempotent upserts of alerts + telemetry into FalkorDB.

Every node is MERGEd on its stable id, so re-running ingestion (or re-POSTing
the same alert) never creates duplicates. INVOLVES / OBSERVED_ON edges carry
provenance properties (alert_id, ts) so every graph fact can be traced back
to the source alert and timestamp.
"""

from __future__ import annotations

from typing import Any

from app.graph.connection import run_query
from app.graph.queries import CREATE_EVENT_REL, CREATE_REL, UPSERT_NODE, UPSERT_NODE_ON_CREATE
from app.ingestion.normalizer import (
    alert_entity_ids,
    ip_scope,
    normalize_account,
    normalize_device,
    normalize_ip,
    normalize_process,
    normalize_service,
)
from app.models import (
    AccountDeviceFact,
    AccountFact,
    AlertAck,
    AlertIn,
    ConnectionFact,
    DemoDataset,
    DeviceFact,
    HistoricalIncidentFact,
    LoginFact,
    ProcessExecutionFact,
    ServiceFact,
)


def upsert_node(label: str, node_id: str, props: dict[str, Any]) -> None:
    run_query(UPSERT_NODE.format(label=label), {"id": node_id, "props": props})


def upsert_rel(src_id: str, rel: str, dst_id: str, props: dict[str, Any] | None = None) -> None:
    run_query(
        CREATE_REL.format(rel=rel),
        {"src_id": src_id, "dst_id": dst_id, "props": props or {}},
    )


def upsert_event_rel(src_id: str, rel: str, dst_id: str, props: dict[str, Any]) -> None:
    """Upsert a timestamped event relationship (unique per event ts)."""
    run_query(
        CREATE_EVENT_REL.format(rel=rel),
        {"src_id": src_id, "dst_id": dst_id, "props": props},
    )


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

def ingest_alert(alert: AlertIn) -> AlertAck:
    """Upsert one alert and its entity edges. Idempotent."""
    entity_ids = alert_entity_ids(alert)
    created_entity_ids: list[str] = []

    # 0) Was this alert already ingested? (drives honest `created` flag)
    existed = bool(
        run_query("MATCH (a:Alert {id: $id}) RETURN a LIMIT 1", {"id": alert.alert_id})
    )

    # 1) The alert node itself (id = source alert id => provenance preserved).
    upsert_node(
        "Alert",
        alert.alert_id,
        {
            "title": alert.title,
            "description": alert.description,
            "severity": alert.severity.value,
            "alert_type": alert.alert_type,
            "ts": alert.timestamp,
            "source": alert.source,
            "tags": alert.tags,
        },
    )

    provenance = {"ts": alert.timestamp, "alert_id": alert.alert_id}

    # 2) Entities referenced by the alert, with INVOLVES edges.
    if entity_ids["actor_account"]:
        aid = entity_ids["actor_account"]
        upsert_node("Account", aid, {"account_name": alert.account})
        upsert_rel(alert.alert_id, "INVOLVES", aid, {**provenance, "role": "actor_account"})
        created_entity_ids.append(aid)

    if entity_ids["observed_device"]:
        did = entity_ids["observed_device"]
        upsert_node("Device", did, {"hostname": alert.device})
        upsert_rel(alert.alert_id, "INVOLVES", did, {**provenance, "role": "observed_device"})
        upsert_rel(alert.alert_id, "OBSERVED_ON", did, provenance)
        created_entity_ids.append(did)

    if entity_ids["source_ip"]:
        ip_id = entity_ids["source_ip"]
        addr = ip_id.split(":", 1)[1]
        upsert_node("IPAddress", ip_id, {"address": addr, "scope": ip_scope(addr)})
        upsert_rel(alert.alert_id, "INVOLVES", ip_id, {**provenance, "role": "source_ip"})
        created_entity_ids.append(ip_id)

    if entity_ids["process"] and alert.process:
        pid = entity_ids["process"]
        upsert_node(
            "Process",
            pid,
            {
                "name": alert.process.name,
                "command_line": alert.process.command_line,
                "sha256": alert.process.sha256,
            },
        )
        upsert_rel(alert.alert_id, "INVOLVES", pid, {**provenance, "role": "process"})
        created_entity_ids.append(pid)

    if entity_ids["service"]:
        sid = entity_ids["service"]
        upsert_node("Service", sid, {"name": alert.service})
        upsert_rel(alert.alert_id, "INVOLVES", sid, {**provenance, "role": "service"})
        created_entity_ids.append(sid)

    return AlertAck(alert_id=alert.alert_id, created=not existed, entity_ids=created_entity_ids)


def ingest_alerts(alerts: list[AlertIn]) -> tuple[int, int, int, list[str]]:
    """Upsert many alerts; returns (accepted, created, updated, entity ids)."""
    all_entities: list[str] = []
    created = 0
    for alert in alerts:
        ack = ingest_alert(alert)
        created += int(ack.created)
        all_entities.extend(ack.entity_ids)
    accepted = len(alerts)
    return accepted, created, accepted - created, sorted(set(all_entities))


# ---------------------------------------------------------------------------
# Telemetry facts (graph backbone)
# ---------------------------------------------------------------------------

def ingest_account(fact: AccountFact) -> None:
    upsert_node(
        "Account",
        fact.id,
        {
            "account_name": fact.id.split(":", 1)[1] if ":" in fact.id else fact.id,
            "display_name": fact.display_name,
            "department": fact.department,
            "role": fact.role,
            "mfa_enrolled": fact.mfa_enrolled,
        },
    )


def ingest_device(fact: DeviceFact) -> None:
    upsert_node(
        "Device",
        fact.id,
        {
            "hostname": fact.hostname or (fact.id.split(":", 1)[1] if ":" in fact.id else fact.id),
            "os": fact.os,
            "device_type": fact.device_type,
            "criticality": fact.criticality,
        },
    )


def ingest_account_device(fact: AccountDeviceFact) -> None:
    upsert_rel(
        fact.account,
        "USED",
        fact.device,
        {"first_seen": fact.first_seen, "last_seen": fact.last_seen, "source": fact.source},
    )


def ingest_login(fact: LoginFact) -> None:
    # Ensure the IP node exists before MATCHing it (keeps ingestion order-agnostic).
    addr = fact.ip.split(":", 1)[1]
    upsert_node("IPAddress", fact.ip, {"address": addr, "scope": ip_scope(addr)})
    upsert_event_rel(
        fact.account,
        "LOGGED_IN_FROM",
        fact.ip,
        {"ts": fact.ts, "success": fact.success, "source": fact.source},
    )


def ingest_process_execution(fact: ProcessExecutionFact) -> None:
    pid = normalize_process(fact.process)
    upsert_node(
        "Process",
        pid,
        {
            "name": fact.process.name,
            "command_line": fact.process.command_line,
            "sha256": fact.process.sha256,
        },
    )
    # RUNS is a timestamped event edge (multiple executions -> parallel edges).
    upsert_event_rel(pid, "RUNS", fact.device, {"ts": fact.ts})


def ingest_connection(fact: ConnectionFact) -> None:
    props = {"ts": fact.ts, "port": fact.port, "proto": fact.proto}
    if fact.dst_device:
        upsert_event_rel(fact.src_device, "CONNECTS_TO", fact.dst_device, props)
    if fact.dst_ip:
        addr = fact.dst_ip.split(":", 1)[1]
        upsert_node("IPAddress", fact.dst_ip, {"address": addr, "scope": ip_scope(addr)})
        upsert_event_rel(fact.src_device, "CONNECTS_TO", fact.dst_ip, props)
    if fact.process_sha256:
        proc_id = f"proc:{fact.process_sha256.lower()[:16]}"
        if fact.dst_ip:
            upsert_event_rel(proc_id, "CONNECTS_TO", fact.dst_ip, props)


def ingest_service(fact: ServiceFact) -> None:
    upsert_node("Service", fact.id, {"name": fact.name or fact.id})
    upsert_rel(fact.id, "RUNS", fact.host_device, {"source": "cmdb"})
    for dep in fact.depends_on:
        upsert_rel(fact.id, "DEPENDS_ON", dep, {"source": "cmdb"})


def ingest_analyst(handle: str, display_name: str = "") -> None:
    upsert_node("Analyst", f"analyst:{handle.lstrip('@')}", {"handle": handle, "display_name": display_name})


def ingest_historical_incident(fact: HistoricalIncidentFact) -> None:
    """Seed a past incident + its stored memories (persistent memory demo).

    Historical alert stubs (Alert nodes created only if missing) keep entity
    provenance uniform: incident -> PART_OF -> alert -> INVOLVES -> entity.
    """
    analyst_id = f"analyst:{fact.analyst.lstrip('@')}"
    upsert_node(
        "Incident",
        fact.id,
        {
            "title": fact.title,
            "summary": fact.summary,
            "severity": fact.severity.value,
            "status": "CLOSED" if fact.closed_at else "OPEN",
            "opened_at": fact.opened_at,
            "closed_at": fact.closed_at,
        },
    )
    upsert_rel(analyst_id, "INVESTIGATED", fact.id, {"started_at": fact.opened_at})

    # Stub alert nodes so historical entities stay queryable with the same
    # path shape as live alerts. Never overwrites an existing real alert.
    for alert_id in fact.alert_ids:
        run_query(
            UPSERT_NODE_ON_CREATE.format(label="Alert"),
            {
                "id": alert_id,
                "props": {
                    "title": f"Historical signal for {fact.id}",
                    "description": fact.summary,
                    "severity": fact.severity.value,
                    "alert_type": "historical",
                    "ts": fact.opened_at,
                    "source": "historical_archive",
                    "historical": True,
                },
            },
        )
        upsert_rel(alert_id, "PART_OF", fact.id, {"grouped_at": fact.opened_at, "historical": True})

    primary_alert = fact.alert_ids[0] if fact.alert_ids else None
    for entity_id in fact.entity_ids:
        if primary_alert:
            upsert_rel(
                primary_alert,
                "INVOLVES",
                entity_id,
                {"ts": fact.opened_at, "alert_id": primary_alert, "role": "historical_entity"},
            )

    for mem in fact.memories:
        upsert_node(
            "Memory",
            mem.id,
            {
                "kind": mem.kind.value,
                "content": mem.content,
                "confidence": mem.confidence,
                "created_at": fact.opened_at,
                "created_by": mem.created_by,
                "historical": True,
            },
        )
        upsert_rel(mem.id, "PART_OF", fact.id, {})
        upsert_rel(analyst_id, "PRODUCED", mem.id, {"ts": fact.opened_at})


# ---------------------------------------------------------------------------
# Full dataset
# ---------------------------------------------------------------------------

def load_demo_dataset(dataset: DemoDataset) -> dict[str, int]:
    """Idempotently load the full synthetic dataset."""
    counts: dict[str, int] = {}

    for analyst in dataset.analysts:
        ingest_analyst(analyst["handle"], analyst.get("display_name", ""))
    counts["analysts"] = len(dataset.analysts)

    for a in dataset.accounts:
        ingest_account(a)
    counts["accounts"] = len(dataset.accounts)

    for d in dataset.devices:
        ingest_device(d)
    counts["devices"] = len(dataset.devices)

    for ad in dataset.account_devices:
        ingest_account_device(ad)
    counts["account_devices"] = len(dataset.account_devices)

    for lg in dataset.logins:
        ingest_login(lg)
    counts["logins"] = len(dataset.logins)

    for pe in dataset.process_executions:
        ingest_process_execution(pe)
    counts["process_executions"] = len(dataset.process_executions)

    for cf in dataset.connections:
        ingest_connection(cf)
    counts["connections"] = len(dataset.connections)

    for sv in dataset.services:
        ingest_service(sv)
    counts["services"] = len(dataset.services)

    n_alerts, _created, _updated, _ents = ingest_alerts(dataset.alerts)
    counts["alerts"] = n_alerts

    for hi in dataset.historical_incidents:
        ingest_historical_incident(hi)
    counts["historical_incidents"] = len(dataset.historical_incidents)

    return counts


def load_demo_dataset_from_path(path: str) -> dict[str, int]:
    """Load and ingest the demo dataset from a JSON file."""
    import json

    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    dataset = DemoDataset.model_validate(raw)
    return load_demo_dataset(dataset)


# Re-export normalizers used by routes.
__all__ = [
    "ingest_alert",
    "ingest_alerts",
    "load_demo_dataset",
    "load_demo_dataset_from_path",
    "upsert_node",
    "upsert_rel",
    "normalize_account",
    "normalize_device",
    "normalize_ip",
    "normalize_service",
]

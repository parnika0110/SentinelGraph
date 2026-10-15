"""Pydantic models: API contracts + ingestion fact schemas.

All alert/telemetry inputs are validated here before touching FalkorDB.
Timestamps are normalized to timezone-aware UTC ISO-8601 strings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"


class ActionType(str, Enum):
    INVESTIGATE_ACCOUNT = "INVESTIGATE_ACCOUNT"
    REVIEW_DEVICE = "REVIEW_DEVICE"
    ISOLATE_DEVICE = "ISOLATE_DEVICE"
    DISABLE_ACCOUNT = "DISABLE_ACCOUNT"
    BLOCK_IP = "BLOCK_IP"
    REVIEW_SERVICE = "REVIEW_SERVICE"


class MemoryKind(str, Enum):
    FINDING = "finding"
    FEEDBACK = "feedback"


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def normalize_ts(value: str | datetime) -> str:
    """Normalize a timestamp to timezone-aware UTC ISO-8601 ('Z' suffix)."""
    if isinstance(value, datetime):
        dt = value
    else:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Alert ingestion
# ---------------------------------------------------------------------------

class ProcessInfo(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    command_line: str = ""
    sha256: str = ""


class AlertIn(BaseModel):
    """A security alert submitted via POST /alerts."""

    alert_id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    title: str = Field(min_length=3, max_length=300)
    description: str = ""
    severity: Severity
    alert_type: str = Field(min_length=2, max_length=80)
    timestamp: str
    source: str = Field(min_length=1, max_length=80)
    account: str | None = None
    device: str | None = None
    source_ip: str | None = None
    process: ProcessInfo | None = None
    service: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("timestamp")
    @classmethod
    def _ts_valid(cls, v: str) -> str:
        return normalize_ts(v)


class AlertAck(BaseModel):
    alert_id: str
    created: bool
    entity_ids: list[str]


class BulkAlertIn(BaseModel):
    alerts: list[AlertIn] = Field(min_length=1, max_length=500)
    replace_incident_memory: bool = False


class BulkAlertAck(BaseModel):
    accepted: int
    created: int
    updated: int
    entity_ids: list[str]


# ---------------------------------------------------------------------------
# Telemetry facts (used by the demo dataset loader; validated, then upserted)
# ---------------------------------------------------------------------------

class AccountFact(BaseModel):
    id: str
    display_name: str = ""
    department: str = ""
    role: str = ""
    mfa_enrolled: bool = True


class DeviceFact(BaseModel):
    id: str
    hostname: str = ""
    os: str = ""
    device_type: str = "workstation"  # workstation | server
    criticality: str = "normal"       # normal | high


class AccountDeviceFact(BaseModel):
    account: str
    device: str
    first_seen: str
    last_seen: str
    source: str = "identity_inventory"


class LoginFact(BaseModel):
    account: str
    ip: str
    ts: str
    success: bool = True
    source: str = "idp"

    @field_validator("ts")
    @classmethod
    def _ts_valid(cls, v: str) -> str:
        return normalize_ts(v)


class ProcessExecutionFact(BaseModel):
    process: ProcessInfo
    device: str
    ts: str

    @field_validator("ts")
    @classmethod
    def _ts_valid(cls, v: str) -> str:
        return normalize_ts(v)


class ConnectionFact(BaseModel):
    src_device: str
    dst_device: str | None = None
    dst_ip: str | None = None
    port: int = Field(ge=0, le=65535)
    proto: str = "tcp"
    ts: str
    process_sha256: str | None = None

    @field_validator("ts")
    @classmethod
    def _ts_valid(cls, v: str) -> str:
        return normalize_ts(v)


class ServiceFact(BaseModel):
    id: str
    name: str = ""
    host_device: str
    depends_on: list[str] = Field(default_factory=list)


class MemoryFact(BaseModel):
    id: str
    kind: MemoryKind
    content: str = Field(min_length=3)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    created_by: str


class HistoricalIncidentFact(BaseModel):
    id: str
    title: str
    summary: str = ""
    severity: Severity = Severity.HIGH
    opened_at: str
    closed_at: str | None = None
    alert_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    analyst: str
    memories: list[MemoryFact] = Field(default_factory=list)

    @field_validator("opened_at")
    @classmethod
    def _ts_valid(cls, v: str) -> str:
        return normalize_ts(v)


class DemoDataset(BaseModel):
    """Shape of data/demo_alerts.json."""

    description: str = ""
    analysts: list[dict[str, str]] = Field(default_factory=list)
    alerts: list[AlertIn]
    accounts: list[AccountFact] = Field(default_factory=list)
    devices: list[DeviceFact] = Field(default_factory=list)
    account_devices: list[AccountDeviceFact] = Field(default_factory=list)
    logins: list[LoginFact] = Field(default_factory=list)
    process_executions: list[ProcessExecutionFact] = Field(default_factory=list)
    connections: list[ConnectionFact] = Field(default_factory=list)
    services: list[ServiceFact] = Field(default_factory=list)
    historical_incidents: list[HistoricalIncidentFact] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Investigation API models
# ---------------------------------------------------------------------------

class InvestigationRequest(BaseModel):
    alert_id: str
    analyst: str = "demo.analyst"


class PathNode(BaseModel):
    id: str
    label: str
    props: dict[str, Any] = Field(default_factory=dict)


class PathEdge(BaseModel):
    type: str
    src: str
    dst: str
    props: dict[str, Any] = Field(default_factory=dict)


class EvidencePath(BaseModel):
    """A real retrieved graph path with full provenance."""

    nodes: list[PathNode]
    edges: list[PathEdge]

    @property
    def source_alert_ids(self) -> list[str]:
        ids = []
        for n in self.nodes:
            if n.label == "Alert":
                ids.append(n.id)
            elif "alert_id" in n.props and isinstance(n.props["alert_id"], str):
                ids.append(n.props["alert_id"])
        return sorted(set(ids))


class EvidenceItem(BaseModel):
    id: str
    kind: str = "graph_path"
    summary: str
    path: EvidencePath | None = None
    source_alert_ids: list[str] = Field(default_factory=list)
    first_seen: str | None = None
    last_seen: str | None = None
    created_at: str


class Hypothesis(BaseModel):
    id: str
    title: str
    statement: str
    classification: str = "hypothesis"   # "observed_fact" | "hypothesis"
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    rationale: str = ""


class HistoricalContext(BaseModel):
    similar_incident_id: str
    title: str = ""
    score: float
    basis: str = ""
    opened_at: str | None = None
    memories: list[dict[str, Any]] = Field(default_factory=list)


class InvestigationResult(BaseModel):
    id: str
    seed_alert_id: str
    created_at: str
    analyst: str
    incident_id: str | None = None
    related_alert_ids: list[str] = Field(default_factory=list)
    excluded_alert_ids: list[dict[str, Any]] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    observed_facts: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    historical_context: list[HistoricalContext] = Field(default_factory=list)
    summary: str = ""
    engine_notes: list[str] = Field(default_factory=list)
    # Chronological events assembled from retrieved graph data (alert timestamps
    # and relationship timestamp properties). Empty if nothing was retrieved.
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    suggested_actions: list[ActionOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Memory API models
# ---------------------------------------------------------------------------

class MemoryIn(BaseModel):
    kind: MemoryKind = MemoryKind.FINDING
    content: str = Field(min_length=3, max_length=4000)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    incident_id: str | None = None
    investigation_id: str | None = None
    created_by: str = "demo.analyst"


class MemoryOut(BaseModel):
    id: str
    kind: str
    content: str
    confidence: float
    incident_id: str | None = None
    investigation_id: str | None = None
    created_by: str
    created_at: str


# ---------------------------------------------------------------------------
# Action API models
# ---------------------------------------------------------------------------

class ActionCreate(BaseModel):
    incident_id: str
    action_type: ActionType
    target_id: str
    description: str = Field(min_length=3, max_length=1000)
    evidence_ids: list[str] = Field(default_factory=list)
    created_by: str = "demo.analyst"


class ActionOut(BaseModel):
    id: str
    incident_id: str
    action_type: str
    target_id: str
    description: str
    status: ActionStatus
    evidence_ids: list[str] = Field(default_factory=list)
    created_by: str
    created_at: str
    decided_at: str | None = None
    decided_by: str | None = None
    decision_reason: str | None = None
    simulated: bool = True


class DecisionIn(BaseModel):
    analyst: str
    reason: str = ""


# ---------------------------------------------------------------------------
# Graph explorer models
# ---------------------------------------------------------------------------

class GraphNode(BaseModel):
    id: str
    label: str
    props: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    type: str
    src: str
    dst: str
    props: dict[str, Any] = Field(default_factory=dict)


class NeighborhoodResponse(BaseModel):
    center_id: str
    hops: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class HealthResponse(BaseModel):
    status: str
    falkordb: str
    graph: str
    counts: dict[str, int] = Field(default_factory=dict)

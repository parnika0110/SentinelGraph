/**
 * Typed client for the SentinelGraph backend.
 *
 * All data shown in the UI comes from these calls -- there are no hardcoded
 * investigation results anywhere in the frontend.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types (mirror the Pydantic response models)
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string;
  falkordb: string;
  graph: string;
  counts: Record<string, number>;
}

export interface AlertSummary {
  id: string;
  title: string;
  severity: "low" | "medium" | "high" | "critical";
  alert_type: string;
  ts: string;
  source: string;
  incident_id: string | null;
  status: "grouped" | "new";
  tags: string[];
}

export interface AlertDetail extends Record<string, unknown> {
  alert: Record<string, unknown>;
  entities: {
    id: string;
    label: string;
    rel: string;
    props: Record<string, unknown>;
    rel_props: Record<string, unknown>;
  }[];
}

export interface PathNode {
  id: string;
  label: string;
  props: Record<string, unknown>;
}

export interface PathEdge {
  type: string;
  src: string;
  dst: string;
  props: Record<string, unknown>;
}

export interface EvidencePath {
  nodes: PathNode[];
  edges: PathEdge[];
}

export interface EvidenceItem {
  id: string;
  kind: string;
  summary: string;
  path: EvidencePath | null;
  source_alert_ids: string[];
  first_seen: string | null;
  last_seen: string | null;
  created_at: string;
}

export interface Hypothesis {
  id: string;
  title: string;
  statement: string;
  classification: "hypothesis" | "observed_fact";
  confidence: number;
  supporting_evidence_ids: string[];
  missing_evidence: string[];
  rationale: string;
}

export interface MemoryItem {
  id: string;
  kind: string;
  content: string;
  confidence: number;
  incident_id: string | null;
  investigation_id: string | null;
  created_by: string;
  created_at: string;
  historical?: boolean;
  trust_note?: string;
}

export interface HistoricalContext {
  similar_incident_id: string;
  title: string;
  score: number;
  basis: string;
  opened_at: string | null;
  memories: MemoryItem[];
}

export type ActionStatus = "PROPOSED" | "APPROVED" | "REJECTED" | "COMPLETED";

export interface ActionOut {
  id: string;
  incident_id: string;
  action_type: string;
  target_id: string;
  description: string;
  status: ActionStatus;
  evidence_ids: string[];
  created_by: string;
  created_at: string;
  decided_at: string | null;
  decided_by: string | null;
  decision_reason: string | null;
  simulated: boolean;
}

export interface ExcludedAlert {
  alert_id: string;
  score: number;
  reason: string;
  breakdown?: Record<string, unknown>;
}

export interface TimelineEvent {
  ts: string;
  kind: string;
  text: string;
  detail?: string;
  source_alert_ids: string[];
  observed: boolean;
}

export interface InvestigationResult {
  id: string;
  seed_alert_id: string;
  created_at: string;
  analyst: string;
  incident_id: string | null;
  related_alert_ids: string[];
  excluded_alert_ids: ExcludedAlert[];
  hypotheses: Hypothesis[];
  observed_facts: string[];
  evidence: EvidenceItem[];
  missing_evidence: string[];
  historical_context: HistoricalContext[];
  summary: string;
  engine_notes: string[];
  timeline: TimelineEvent[];
  suggested_actions: ActionOut[];
}

export interface GraphNode {
  id: string;
  label: string;
  props: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  type: string;
  src: string;
  dst: string;
  props: Record<string, unknown>;
}

export interface NeighborhoodResponse {
  center_id: string;
  hops: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiError(
      0,
      `Cannot reach backend at ${API_BASE} (${(err as Error).message})`,
    );
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  alerts: (params?: { severity?: string; ungrouped_only?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.severity) q.set("severity", params.severity);
    if (params?.ungrouped_only) q.set("ungrouped_only", "true");
    const qs = q.toString();
    return request<{ count: number; alerts: AlertSummary[] }>(`/alerts${qs ? `?${qs}` : ""}`);
  },

  alertDetail: (id: string) => request<AlertDetail>(`/alerts/${encodeURIComponent(id)}`),

  runInvestigation: (alert_id: string, analyst: string) =>
    request<InvestigationResult>("/investigations", {
      method: "POST",
      body: JSON.stringify({ alert_id, analyst }),
    }),

  investigation: (id: string) =>
    request<InvestigationResult>(`/investigations/${encodeURIComponent(id)}`),

  neighborhood: (id: string, hops = 2) =>
    request<NeighborhoodResponse>(
      `/graph/neighborhood/${encodeURIComponent(id)}?hops=${hops}`,
    ),

  memories: (incident_id?: string) =>
    request<{ count: number; memories: MemoryItem[] }>(
      `/memories${incident_id ? `?incident_id=${encodeURIComponent(incident_id)}` : ""}`,
    ),

  postMemory: (payload: {
    kind: "finding" | "feedback";
    content: string;
    confidence?: number;
    incident_id?: string | null;
    investigation_id?: string | null;
    created_by: string;
  }) =>
    request<MemoryItem>("/memories", {
      method: "POST",
      body: JSON.stringify({ confidence: 0.7, ...payload }),
    }),

  actions: (incident_id: string) =>
    request<{ count: number; actions: ActionOut[] }>(
      `/actions?incident_id=${encodeURIComponent(incident_id)}`,
    ),

  decide: (action_id: string, decision: "approve" | "reject", analyst: string, reason: string) =>
    request<ActionOut>(`/actions/${encodeURIComponent(action_id)}/${decision}`, {
      method: "POST",
      body: JSON.stringify({ analyst, reason }),
    }),
};

"use client";

import { useState } from "react";
import {
  Brain,
  ChevronRight,
  Clock,
  FileSearch,
  GitBranch,
  History,
  Lightbulb,
  ListChecks,
  Network,
  TriangleAlert,
} from "lucide-react";;
import {
  Badge,
  ErrorState,
  EmptyState,
  LABEL_STYLES,
  LoadingState,
  Mono,
  SectionCard,
  SeverityBadge,
} from "@/components/ui";
import type { AlertSummary, EvidenceItem, InvestigationResult } from "@/lib/api";

// ---------------------------------------------------------------------------
// Hypothesis card: statement + confidence + evidence + uncertainty + rationale
// ---------------------------------------------------------------------------

function HypothesisCard({ h }: { h: InvestigationResult["hypotheses"][number] }) {
  const pct = Math.round(h.confidence * 100);
  return (
    <div className="rounded-md border border-white/10 bg-slate-950/50 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Lightbulb className="h-4 w-4 text-amber-400" />
          <p className="text-sm font-medium text-slate-100">{h.title}</p>
        </div>
        <Badge
          className={
            h.classification === "observed_fact"
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
              : "border-amber-500/40 bg-amber-500/10 text-amber-300"
          }
        >
          {h.classification === "observed_fact" ? "observed fact" : "hypothesis"}
        </Badge>
      </div>

      <p className="mt-2 text-xs leading-relaxed text-slate-300">{h.statement}</p>

      {/* Confidence bar */}
      <div className="mt-3">
        <div className="mb-1 flex items-center justify-between text-[10px] text-slate-500">
          <span>confidence</span>
          <span className="font-mono text-slate-300">{pct}%</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
          <div
            className={`h-full rounded-full ${pct >= 70 ? "bg-emerald-500" : pct >= 45 ? "bg-amber-500" : "bg-slate-500"}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Rationale (score breakdown) */}
      <details className="mt-2">
        <summary className="cursor-pointer text-[10px] uppercase tracking-wider text-slate-500 hover:text-slate-400">
          why this score (transparent criteria)
        </summary>
        <p className="mt-1.5 rounded bg-slate-900 p-2 font-mono text-[10px] leading-relaxed text-slate-400">
          {h.rationale}
        </p>
      </details>

      {/* Uncertainty */}
      {h.missing_evidence.length > 0 && (
        <div className="mt-2 rounded border border-amber-500/20 bg-amber-500/5 p-2">
          <p className="mb-1 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-amber-400">
            <TriangleAlert className="h-3 w-3" /> uncertainty / missing evidence
          </p>
          <ul className="space-y-0.5">
            {h.missing_evidence.map((m, i) => (
              <li key={i} className="text-[11px] text-amber-200/80">
                • {m}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="mt-2 text-[10px] text-slate-500">
        evidence: {h.supporting_evidence_ids.join(", ") || "none"}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Evidence path renderer: node chips + relationship chips (provenance)
// ---------------------------------------------------------------------------

function EvidencePathView({ ev }: { ev: EvidenceItem }) {
  if (!ev.path) return null;
  const { nodes, edges } = ev.path;
  return (
    <div className="rounded-md border border-white/10 bg-slate-950/50 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <Badge className="border-cyan-500/40 bg-cyan-500/10 text-cyan-300">
          {nodes.length - 1} hops
        </Badge>
        {ev.source_alert_ids.map((a) => (
          <Badge key={a} className="border-rose-500/40 bg-rose-500/10 text-rose-300">
            {a}
          </Badge>
        ))}
        {ev.first_seen && (
          <span className="text-[10px] text-slate-500">
            {ev.first_seen} → {ev.last_seen}
          </span>
        )}
      </div>

      <div className="space-y-1.5">
        {nodes.map((n, i) => (
          <div key={`${n.id}-${i}`}>
            <div className="flex items-center gap-2">
              <span
                className={`rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase ${LABEL_STYLES[n.label] ?? "border-slate-500/40 bg-slate-500/10 text-slate-300"}`}
              >
                {n.label}
              </span>
              <Mono>
                <span className="text-slate-300">{n.id}</span>
              </Mono>
              {(n.props.severity as string) && (
                <SeverityBadge severity={String(n.props.severity)} />
              )}
            </div>
            {i < edges.length && (
              <div className="my-0.5 flex items-center gap-2 pl-3">
                <ChevronRight className="h-3 w-3 text-slate-600" />
                <span className="font-mono text-[10px] text-sky-400">
                  -[{edges[i].type}]-&gt;
                </span>
                {(edges[i].props.ts as string) && (
                  <span className="text-[10px] text-slate-500">
                    @ {String(edges[i].props.ts)}
                  </span>
                )}
                {(edges[i].props.role as string) && (
                  <span className="text-[10px] text-slate-600">
                    role: {String(edges[i].props.role)}
                  </span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

export default function InvestigationView({
  result,
  loading,
  error,
  selectedAlert,
  onSelectAlert,
  onOpenNode,
}: {
  result: InvestigationResult | null;
  loading: boolean;
  error: string | null;
  selectedAlert: AlertSummary | null;
  onSelectAlert: (id: string) => void;
  onOpenNode: (id: string) => void;
}) {
  const [tab, setTab] = useState<"evidence" | "timeline" | "graph-notes">("evidence");

  if (error) return <ErrorState message={error} />;
  if (loading)
    return <LoadingState label="Running bounded multi-hop traversal in FalkorDB" />;
  if (!result)
    return (
      <EmptyState
        title="No investigation selected"
        hint="Pick an alert from the queue, then press Run investigation to traverse its graph neighborhood and correlate neighboring alerts."
      />
    );

  const linkedEvidence = result.evidence.filter(
    (e) => e.path && e.path.nodes.length >= 3 && e.source_alert_ids.length >= 2,
  );

  return (
    <div className="space-y-3">
      {/* Header */}
      <SectionCard
        title="Investigation result"
        icon={<Network className="h-3.5 w-3.5" />}
        right={
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge className="border-rose-500/40 bg-rose-500/10 text-rose-300">
              seed {result.seed_alert_id}
            </Badge>
            {result.incident_id && (
              <Badge className="border-fuchsia-500/40 bg-fuchsia-500/10 text-fuchsia-300">
                {result.incident_id}
              </Badge>
            )}
            <span className="text-[10px] text-slate-500">
              {result.created_at} · {result.analyst}
            </span>
          </div>
        }
      >
        <div className="flex flex-wrap gap-2 text-xs">
          <div className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-emerald-300">
            grouped: {result.related_alert_ids.length
              ? result.related_alert_ids.join(", ")
              : "none"}
          </div>
          <div className="rounded border border-slate-500/30 bg-slate-500/10 px-2 py-1 text-slate-400">
            excluded: {result.excluded_alert_ids.length}
          </div>
          <div className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-amber-300">
            gaps: {result.missing_evidence.length}
          </div>
        </div>
        <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-slate-400">
          {result.summary}
        </p>
      </SectionCard>

      {/* Observed facts vs hypotheses */}
      <SectionCard
        title="Observed facts (retrieved from graph)"
        icon={<ListChecks className="h-3.5 w-3.5" />}
      >
        <ul className="space-y-1">
          {result.observed_facts.slice(0, 8).map((f, i) => (
            <li key={i} className="flex gap-2 text-xs text-slate-300">
              <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-emerald-400" />
              <span className="font-mono text-[11px] leading-relaxed">{f}</span>
            </li>
          ))}
        </ul>
      </SectionCard>

      <SectionCard
        title="Hypotheses (inferred, uncertainty stated)"
        icon={<Brain className="h-3.5 w-3.5" />}
      >
        <div className="space-y-2.5">
          {result.hypotheses.map((h) => (
            <HypothesisCard key={h.id} h={h} />
          ))}
        </div>
      </SectionCard>

      {/* Related incidents + historical memory (retrieved via SIMILAR_TO) */}
      {result.historical_context.length > 0 && (
        <SectionCard
          title="Related incidents & historical memory"
          icon={<History className="h-3.5 w-3.5" />}
          right={
            <Badge className="border-indigo-500/40 bg-indigo-500/10 text-indigo-300">
              {result.historical_context.length} similar
            </Badge>
          }
        >
          <div className="space-y-2.5">
            {result.historical_context.map((h) => (
              <div
                key={h.similar_incident_id}
                className="rounded-md border border-white/10 bg-slate-950/50 p-2.5"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Badge className="border-fuchsia-500/40 bg-fuchsia-500/10 text-fuchsia-300">
                      {h.similar_incident_id}
                    </Badge>
                    <span className="text-xs font-medium text-slate-200">
                      {h.title || "(untitled incident)"}
                    </span>
                  </div>
                  <span className="font-mono text-[10px] text-slate-500">
                    similarity {h.score.toFixed(2)} · {h.opened_at ?? "date n/a"}
                  </span>
                </div>
                <p className="mt-1 font-mono text-[10px] text-slate-500">
                  basis: {h.basis}
                </p>

                <div className="mt-2 space-y-1.5">
                  {h.memories.length === 0 && (
                    <p className="text-[11px] text-slate-600">
                      No stored findings on this incident.
                    </p>
                  )}
                  {h.memories.map((m) => (
                    <div
                      key={m.id}
                      className="rounded border border-white/5 bg-slate-900/70 p-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <Badge className="border-slate-500/40 bg-slate-500/10 text-slate-400">
                          {m.kind}
                        </Badge>
                        <span className="text-[10px] text-slate-600">
                          {m.created_by} · {m.created_at}
                        </span>
                      </div>
                      <p className="mt-1 text-[11px] leading-relaxed text-slate-300">
                        {m.content}
                      </p>
                      {m.trust_note && (
                        <p className="mt-1 flex items-start gap-1 text-[10px] italic text-amber-400/90">
                          <TriangleAlert className="mt-0.5 h-3 w-3 shrink-0" />
                          {m.trust_note}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[10px] text-slate-600">
            Historical memory is context retrieved through SIMILAR_TO edges in
            FalkorDB -- earlier hypotheses stay hypotheses, never confirmed
            truth for this incident.
          </p>
        </SectionCard>
      )}

      {/* Excluded candidates (why NOT grouped) */}
      {result.excluded_alert_ids.length > 0 && (
        <SectionCard
          title="Evaluated and excluded candidates"
          icon={<TriangleAlert className="h-3.5 w-3.5" />}
        >
          <div className="space-y-2">
            {result.excluded_alert_ids.map((ex) => (
              <div
                key={ex.alert_id}
                className="rounded border border-white/10 bg-slate-950/50 p-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <button
                    onClick={() => onOpenNode(ex.alert_id)}
                    className="font-mono text-[11px] text-sky-400 hover:underline"
                  >
                    {ex.alert_id}
                  </button>
                  <span className="font-mono text-[10px] text-slate-500">
                    score {ex.score}
                  </span>
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-400">
                  {ex.reason}
                </p>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      {/* Tabs: evidence paths / timeline / engine notes */}
      <SectionCard
        title="Evidence & provenance"
        icon={<FileSearch className="h-3.5 w-3.5" />}
        right={
          <div className="flex gap-1">
            {(
              [
                ["evidence", "Paths"],
                ["timeline", "Timeline"],
                ["graph-notes", "Engine"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={`rounded px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
                  tab === key
                    ? "bg-sky-500/20 text-sky-300"
                    : "text-slate-500 hover:text-slate-300"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        }
      >
        {tab === "evidence" && (
          <div className="space-y-2.5">
            {linkedEvidence.length === 0 && result.evidence.length === 0 && (
              <EmptyState title="No evidence retrieved" />
            )}
            {result.evidence.map((ev) => (
              <EvidencePathView key={ev.id} ev={ev} />
            ))}
          </div>
        )}

        {tab === "timeline" && (
          <div className="relative space-y-2 border-l border-slate-700 pl-4">
            {result.timeline.length === 0 && (
              <p className="text-xs text-slate-500">No timestamped evidence retrieved.</p>
            )}
            {result.timeline.map((e, i) => (
              <div key={i} className="relative">
                <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full border border-slate-900 bg-sky-400" />
                <div className="flex items-center gap-2">
                  <Clock className="h-3 w-3 text-slate-500" />
                  <span className="font-mono text-[10px] text-sky-400">{e.ts}</span>
                  <Badge className="border-slate-500/40 bg-slate-500/10 text-slate-400">
                    {e.kind}
                  </Badge>
                  {e.observed && (
                    <span className="text-[9px] uppercase text-emerald-400/80">
                      observed
                    </span>
                  )}
                </div>
                <button
                  onClick={() =>
                    onOpenNode(e.source_alert_ids[0] ?? result.seed_alert_id)
                  }
                  className="mt-0.5 block text-left font-mono text-[11px] text-slate-300 hover:text-sky-300"
                >
                  {e.text}
                </button>
              </div>
            ))}
          </div>
        )}

        {tab === "graph-notes" && (
          <div className="space-y-1.5">
            {result.engine_notes.map((n, i) => (
              <p
                key={i}
                className="rounded bg-slate-950/60 p-2 font-mono text-[10px] leading-relaxed text-slate-400"
              >
                {n}
              </p>
            ))}
          </div>
        )}
      </SectionCard>

      {/* Quick jump to grouped alerts */}
      {selectedAlert && result.related_alert_ids.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <GitBranch className="h-3.5 w-3.5" />
          jump to grouped alert:
          {result.related_alert_ids.map((id) => (
            <button
              key={id}
              onClick={() => onSelectAlert(id)}
              className="rounded border border-white/10 px-1.5 py-0.5 font-mono text-[10px] text-sky-400 hover:bg-sky-500/10"
            >
              {id}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

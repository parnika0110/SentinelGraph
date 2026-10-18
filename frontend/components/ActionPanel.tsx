"use client";

import { useCallback, useRef, useState } from "react";
import {
  CheckCircle2,
  ClipboardCheck,
  Database,
  Loader2,
  Save,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { Badge, EmptyState, ErrorState, SectionCard } from "@/components/ui";
import { api, type ActionOut, type MemoryItem } from "@/lib/api";

const STATUS_STYLES: Record<string, string> = {
  PROPOSED: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  APPROVED: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  REJECTED: "border-rose-500/40 bg-rose-500/10 text-rose-300",
  COMPLETED: "border-zinc-500/40 bg-zinc-500/10 text-zinc-300",
};

// ---------------------------------------------------------------------------
// Recommended actions with explicit approval gate
// ---------------------------------------------------------------------------

export function ActionPanel({
  incidentId,
  actions,
  onActionsChanged,
  analyst,
}: {
  incidentId: string | null;
  actions: ActionOut[];
  onActionsChanged: (actions: ActionOut[]) => void;
  analyst: string;
}) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Two-step decision: first click stages the decision, second click submits it.
  // The stage records which incident it belongs to so it never leaks across
  // incidents, and it is only cleared on success (or explicit cancel) so an
  // API error cannot silently discard the analyst's intent.
  const [pending, setPending] = useState<{
    incident: string;
    id: string;
    decision: "approve" | "reject";
  } | null>(null);
  const stageButtonRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const decide = useCallback(
    async (id: string, decision: "approve" | "reject") => {
      if (busyId) return; // block double submission
      setBusyId(id);
      setError(null);
      try {
        await api.decide(id, decision, analyst, `${decision} via SentinelGraph dashboard`);
        const refreshed = await api.actions(incidentId!);
        onActionsChanged(refreshed.actions);
        setPending(null); // clear only after a successful submit
      } catch (err) {
        // Keep the staged decision visible so it is not lost; the analyst can retry.
        setError((err as Error).message);
      } finally {
        setBusyId(null);
      }
    },
    [analyst, busyId, incidentId, onActionsChanged],
  );

  const stage = useCallback((id: string, decision: "approve" | "reject") => {
    setPending({ incident: incidentId ?? "", id, decision });
  }, [incidentId]);

  const cancelStaged = useCallback(() => {
    if (!pending) return;
    const key = `${pending.id}:${pending.decision}`;
    setPending(null);
    // Return keyboard focus to the button that started the staged decision
    // once it re-mounts.
    window.setTimeout(() => stageButtonRefs.current[key]?.focus(), 0);
  }, [pending]);

  if (!incidentId)
    return (
      <SectionCard title="Recommended actions" icon={<ShieldCheck className="h-3.5 w-3.5" />}>
        <EmptyState
          title="No incident yet"
          hint="Actions are proposed only after an investigation groups alerts into an incident."
        />
      </SectionCard>
    );

  return (
    <SectionCard
      title="Recommended actions (simulated)"
      icon={<ShieldCheck className="h-3.5 w-3.5" />}
      right={
        <Badge className="border-amber-500/40 bg-amber-500/10 text-amber-300">
          approval required
        </Badge>
      }      >
      {error && (
        <div role="alert" className="mt-2">
          <ErrorState message={error} />
        </div>
      )}
      {actions.length === 0 && (
        <p className="text-xs text-slate-500">No proposals for this incident.</p>
      )}
      <div className="space-y-2">
        {actions.map((a) => (
          <div
            key={a.id}
            className="rounded-sm border border-white/10 bg-slate-950/50 p-2.5"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] font-medium text-slate-200">
                  {a.action_type}
                </span>
                <Badge className={STATUS_STYLES[a.status]}>{a.status}</Badge>
              </div>
              <span className="font-mono text-[10px] text-slate-500">{a.target_id}</span>
            </div>
            <p className="mt-1 text-[11px] leading-relaxed text-slate-400">
              {a.description}
            </p>

            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <span className="text-[10px] text-slate-600">
                proposed {a.created_at} by {a.created_by}
                {a.decided_by && ` · decided by ${a.decided_by}`}
              </span>
              {a.status === "PROPOSED" &&
                pending &&
                pending.id === a.id &&
                pending.incident === incidentId && (
                <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={`Confirm ${pending.decision} for ${a.action_type}`}>
                  <span className="text-[10px] text-slate-400">
                    {pending.decision} this simulated action? ({a.action_type} → {a.target_id})
                  </span>
                  <button
                    autoFocus
                    onClick={() => decide(a.id, pending.decision)}
                    disabled={busyId !== null}
                    className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-[10px] font-semibold uppercase tracking-wide disabled:opacity-50 ${pending.decision === "approve" ? "border-emerald-500/50 bg-emerald-500/20 text-emerald-300" : "border-rose-500/50 bg-rose-500/20 text-rose-300"}`}
                  >
                    {busyId === a.id && <Loader2 className="h-3 w-3 animate-spin" />}
                    confirm {pending.decision}
                  </button>
                  <button
                    onClick={cancelStaged}
                    disabled={busyId !== null}
                    className="rounded border border-[var(--border)] px-2 py-1 text-[10px] uppercase tracking-wide text-slate-400 hover:bg-white/5"
                  >
                    cancel
                  </button>
                </div>
              )}
              {a.status === "PROPOSED" &&
                !(pending && pending.id === a.id && pending.incident === incidentId) && (
                <div className="flex gap-1.5">
                  <button
                    ref={(el) => {
                      stageButtonRefs.current[`${a.id}:approve`] = el;
                    }}
                    onClick={() => stage(a.id, "approve")}
                    disabled={busyId !== null}
                    className="inline-flex items-center gap-1 rounded border border-emerald-500/50 bg-emerald-500/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-50"
                  >
                    <CheckCircle2 className="h-3 w-3" />
                    approve
                  </button>
                  <button
                    ref={(el) => {
                      stageButtonRefs.current[`${a.id}:reject`] = el;
                    }}
                    onClick={() => stage(a.id, "reject")}
                    disabled={busyId !== null}
                    className="inline-flex items-center gap-1 rounded border border-rose-500/50 bg-rose-500/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-rose-300 hover:bg-rose-500/20 disabled:opacity-50"
                  >
                    <XCircle className="h-3 w-3" />
                    reject
                  </button>
                </div>
              )}
            </div>
            {a.decision_reason && (
              <p className="mt-1 text-[10px] italic text-slate-500">
                decision: {a.decision_reason}
              </p>
            )}
          </div>
        ))}
      </div>
      <p className="mt-2 flex items-center gap-1 text-[10px] text-slate-600">
        <ClipboardCheck className="h-3 w-3" />
        All actions are simulated. Nothing is executed against real systems; a
        PROPOSED action never changes state without an explicit analyst approval.
      </p>
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// Incident memory: historical context + stored findings + analyst feedback
// ---------------------------------------------------------------------------

export function MemoryPanel({
  incidentId,
  memories,
  onMemoryPosted,
  analyst,
}: {
  incidentId: string | null;
  memories: MemoryItem[];
  onMemoryPosted: () => void;
  analyst: string;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!incidentId || text.trim().length < 3 || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.postMemory({
        kind: "feedback",
        content: text.trim(),
        incident_id: incidentId,
        created_by: analyst,
      });
      setText("");
      onMemoryPosted();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <SectionCard
      title="Incident memory"
      icon={<Database className="h-3.5 w-3.5" />}
      right={
        <Badge className="border-indigo-500/40 bg-indigo-500/10 text-indigo-300">
          persisted in FalkorDB
        </Badge>
      }
    >
      {error && <div className="mb-2"><ErrorState message={error} /></div>}

      {!incidentId && (
        <EmptyState
          title="No incident linked"
          hint="Stored findings and analyst feedback appear once an investigation creates an incident."
        />
      )}

      {incidentId && (
        <>
          <div className="max-h-44 space-y-2 overflow-y-auto pr-1">
            {memories.length === 0 && (
              <p className="text-xs text-slate-500">
                No memories stored for this incident yet.
              </p>
            )}
            {memories.map((m) => (
              <div
                key={m.id}
                className="rounded border border-white/10 bg-slate-950/50 p-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <Badge
                    className={
                      m.kind === "finding"
                        ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                        : "border-violet-500/40 bg-violet-500/10 text-violet-300"
                    }
                  >
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
                  <p className="mt-1 text-[10px] italic text-amber-400/80">
                    {m.trust_note}
                  </p>
                )}
                {typeof m.confidence === "number" && (
                  <p className="mt-0.5 text-[10px] text-slate-600">
                    confidence {Math.round(m.confidence * 100)}%
                  </p>
                )}
              </div>
            ))}
          </div>

          <div className="mt-2 flex gap-1.5">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={2}
              placeholder="Record analyst feedback for future investigations..."
              className="flex-1 resize-none rounded border border-white/10 bg-slate-950/60 px-2 py-1.5 text-[11px] text-slate-200 placeholder:text-slate-600 focus:border-[var(--accent)]"
            />
            <button
              onClick={submit}
              disabled={busy || text.trim().length < 3}
              className="inline-flex items-center gap-1 self-end rounded border border-indigo-500/50 bg-indigo-500/10 px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-300 hover:bg-indigo-500/20 disabled:opacity-40"
            >
              {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
              store
            </button>
          </div>
        </>
      )}
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// Small spinner re-export used by page header
// ---------------------------------------------------------------------------

export function InlineSpinner() {
  return <Loader2 className="h-3.5 w-3.5 animate-spin" />;
}

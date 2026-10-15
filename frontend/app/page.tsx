"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  Database,
  Filter,
  Play,
  RefreshCw,
  Search,
  Shield,
} from "lucide-react";
import GraphExplorer from "@/components/GraphExplorer";
import InvestigationView from "@/components/InvestigationView";
import { ActionPanel, MemoryPanel } from "@/components/ActionPanel";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  QueueRow,
} from "@/components/ui";
import {
  api,
  type ActionOut,
  type AlertSummary,
  type HealthResponse,
  type InvestigationResult,
  type MemoryItem,
  type NeighborhoodResponse,
} from "@/lib/api";

const SEVERITIES = ["critical", "high", "medium", "low"] as const;

export default function Dashboard() {
  // --- global/system state -------------------------------------------------
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [analyst, setAnalyst] = useState("demo.analyst");

  // --- alert queue ---------------------------------------------------------
  const [alerts, setAlerts] = useState<AlertSummary[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [alertsError, setAlertsError] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState<string | null>(null);
  const [newOnly, setNewOnly] = useState(false);
  const [queueSearch, setQueueSearch] = useState("");

  // --- investigation -------------------------------------------------------
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [investigation, setInvestigation] = useState<InvestigationResult | null>(null);
  const [invLoading, setInvLoading] = useState(false);
  const [invError, setInvError] = useState<string | null>(null);

  // --- graph explorer ------------------------------------------------------
  const [graphCenter, setGraphCenter] = useState<string | null>(null);
  const [graphData, setGraphData] = useState<NeighborhoodResponse | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);

  // --- actions & memory ----------------------------------------------------
  const [actions, setActions] = useState<ActionOut[]>([]);
  const [memories, setMemories] = useState<MemoryItem[]>([]);

  // -------------------------------------------------------------------------
  // Loaders
  // -------------------------------------------------------------------------

  const loadHealth = useCallback(async () => {
    try {
      const h = await api.health();
      setHealth(h);
      setHealthError(null);
    } catch (err) {
      setHealthError((err as Error).message);
    }
  }, []);

  const loadAlerts = useCallback(async () => {
    try {
      const res = await api.alerts();
      setAlerts(res.alerts);
      setAlertsError(null);
      setAlertsLoading(false);
    } catch (err) {
      setAlertsError((err as Error).message);
      setAlertsLoading(false);
    }
  }, []);

  const loadGraph = useCallback(async (center: string | null) => {
    if (!center) return;
    setGraphLoading(true);
    try {
      setGraphData(await api.neighborhood(center, 2));
      setGraphError(null);
    } catch (err) {
      setGraphError((err as Error).message);
      setGraphData(null);
    } finally {
      setGraphLoading(false);
    }
  }, []);

  const loadActionsAndMemories = useCallback(
    async (incidentId: string | null) => {
      if (!incidentId) {
        setActions([]);
        setMemories([]);
        return;
      }
      try {
        const [a, m] = await Promise.all([
          api.actions(incidentId),
          api.memories(incidentId),
        ]);
        setActions(a.actions);
        setMemories(m.memories);
      } catch {
        /* panel-level errors are surfaced on the next explicit action */
      }
    },
    [],
  );

  useEffect(() => {
    // Kick off the initial loads from a microtask so the effect body itself
    // performs no state updates (react-hooks/set-state-in-effect).
    const boot = () => {
      void loadHealth();
      void loadAlerts();
    };
    const t1 = setTimeout(boot, 0);
    const t2 = setInterval(() => void loadHealth(), 15000);
    return () => {
      clearTimeout(t1);
      clearInterval(t2);
    };
  }, [loadHealth, loadAlerts]);

  // -------------------------------------------------------------------------
  // Interactions
  // -------------------------------------------------------------------------

  const selectAlert = useCallback(
    (id: string) => {
      setSelectedAlertId(id);
      setGraphCenter(id);
      void loadGraph(id);
      if (investigation && investigation.seed_alert_id !== id) {
        setInvestigation(null);
        setInvError(null);
        setActions([]);
        setMemories([]);
      }
    },
    [investigation, loadGraph],
  );

  const openNode = useCallback(
    (id: string) => {
      setGraphCenter(id);
      void loadGraph(id);
    },
    [loadGraph],
  );

  const runInvestigation = useCallback(async () => {
    if (!selectedAlertId) return;
    setInvLoading(true);
    setInvError(null);
    setAlertsLoading(true);
    try {
      const res = await api.runInvestigation(selectedAlertId, analyst);
      setInvestigation(res);
      // New incident edges exist now: refresh queue, graph, actions, memory.
      void loadAlerts();
      void loadGraph(res.seed_alert_id);
      setGraphCenter(res.seed_alert_id);
      void loadActionsAndMemories(res.incident_id);
    } catch (err) {
      setInvError((err as Error).message);
      setInvestigation(null);
    } finally {
      setInvLoading(false);
      setAlertsLoading(false);
    }
  }, [selectedAlertId, analyst, loadAlerts, loadGraph, loadActionsAndMemories]);

  const filteredAlerts = useMemo(() => {
    const q = queueSearch.trim().toLowerCase();
    return alerts.filter((a) => {
      if (severityFilter && a.severity !== severityFilter) return false;
      if (newOnly && a.status !== "new") return false;
      if (q && !(`${a.id} ${a.title} ${a.alert_type}`.toLowerCase().includes(q)))
        return false;
      return true;
    });
  }, [alerts, severityFilter, newOnly, queueSearch]);

  const selectedAlert =
    alerts.find((a) => a.id === selectedAlertId) ?? null;

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* ---------------- header ---------------- */}
      <header className="flex items-center justify-between gap-4 border-b border-white/10 bg-slate-950/70 px-4 py-2.5 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-sky-500/15 border border-sky-500/40">
            <Shield className="h-4 w-4 text-sky-400" />
          </div>
          <div>
            <h1 className="text-sm font-semibold tracking-tight text-slate-100">
              SentinelGraph
            </h1>
            <p className="text-[10px] text-slate-500">
              graph-powered incident investigation · FalkorDB
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* health pill */}
          {healthError ? (
            <span className="inline-flex items-center gap-1.5 rounded border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-[10px] font-medium text-rose-300">
              <Activity className="h-3 w-3" /> backend offline
            </span>
          ) : health ? (
            <span className="inline-flex items-center gap-1.5 rounded border border-emerald-500/40 bg-emerald-500/10 px-2 py-1 text-[10px] font-medium text-emerald-300">
              <Activity className="h-3 w-3" />
              {health.status} · {health.falkordb} · {health.graph}
            </span>
          ) : (
            <span className="text-[10px] text-slate-500">checking backend…</span>
          )}

          <label className="flex items-center gap-1.5 text-[10px] text-slate-500">
            analyst
            <input
              value={analyst}
              onChange={(e) => setAnalyst(e.target.value)}
              className="w-28 rounded border border-white/10 bg-slate-950/60 px-2 py-1 font-mono text-[11px] text-slate-300 focus:border-sky-500/50 focus:outline-none"
            />
          </label>

          <button
            onClick={() => {
              setAlertsLoading(true);
              void loadHealth();
              void loadAlerts();
              void loadGraph(graphCenter);
            }}
            className="inline-flex items-center gap-1 rounded border border-white/10 px-2 py-1.5 text-[10px] uppercase tracking-wide text-slate-400 hover:bg-white/5"
          >
            <RefreshCw className="h-3 w-3" /> refresh
          </button>
        </div>
      </header>

      {/* ---------------- main grid ---------------- */}
      <main className="grid flex-1 grid-cols-1 gap-3 overflow-hidden p-3 lg:grid-cols-[280px_1fr] xl:grid-cols-[280px_1fr_400px]">
        {/* ------- left: incident queue ------- */}
        <aside className="flex min-h-0 flex-col rounded-lg border border-white/10 bg-slate-900/60">
          <header className="border-b border-white/10 px-3 py-2">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                <Filter className="h-3.5 w-3.5" /> Incident queue
              </h2>
              <span className="font-mono text-[10px] text-slate-500">
                {filteredAlerts.length}/{alerts.length}
              </span>
            </div>

            {/* search */}
            <div className="mt-2 flex items-center gap-1.5 rounded border border-white/10 bg-slate-950/60 px-2 py-1">
              <Search className="h-3 w-3 text-slate-500" />
              <input
                value={queueSearch}
                onChange={(e) => setQueueSearch(e.target.value)}
                placeholder="search alerts…"
                className="w-full bg-transparent text-[11px] text-slate-300 placeholder:text-slate-600 focus:outline-none"
              />
            </div>

            {/* severity filters */}
            <div className="mt-2 flex flex-wrap gap-1">
              <button
                onClick={() => setSeverityFilter(null)}
                className={`rounded px-1.5 py-0.5 text-[10px] uppercase ${
                  severityFilter === null
                    ? "bg-sky-500/20 text-sky-300"
                    : "text-slate-500 hover:text-slate-300"
                }`}
              >
                all
              </button>
              {SEVERITIES.map((s) => (
                <button
                  key={s}
                  onClick={() => setSeverityFilter(severityFilter === s ? null : s)}
                  className={`rounded px-1.5 py-0.5 text-[10px] uppercase ${
                    severityFilter === s
                      ? "bg-sky-500/20 text-sky-300"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {s}
                </button>
              ))}
              <button
                onClick={() => setNewOnly((v) => !v)}
                className={`ml-auto rounded px-1.5 py-0.5 text-[10px] uppercase ${
                  newOnly
                    ? "bg-amber-500/20 text-amber-300"
                    : "text-slate-500 hover:text-slate-300"
                }`}
              >
                new only
              </button>
            </div>
          </header>

          <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-2">
            {alertsLoading && <LoadingState label="Loading alerts" />}
            {alertsError && <ErrorState message={alertsError} />}
            {!alertsLoading && !alertsError && filteredAlerts.length === 0 && (
              <EmptyState title="No alerts match the filters" />
            )}
            {filteredAlerts.map((a) => (
              <QueueRow
                key={a.id}
                alert={a}
                selected={a.id === selectedAlertId}
                onSelect={() => selectAlert(a.id)}
              />
            ))}
          </div>

          {/* run bar */}
          <div className="border-t border-white/10 p-2">
            <button
              onClick={() => void runInvestigation()}
              disabled={!selectedAlertId || invLoading}
              className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-sky-500/15 border border-sky-500/50 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-sky-300 hover:bg-sky-500/25 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {invLoading ? (
                <>
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" /> traversing…
                </>
              ) : (
                <>
                  <Play className="h-3.5 w-3.5" /> Run investigation
                </>
              )}
            </button>
            <p className="mt-1.5 text-center text-[10px] text-slate-600">
              {selectedAlertId
                ? `seed: ${selectedAlertId}`
                : "select an alert to investigate"}
            </p>
          </div>
        </aside>

        {/* ------- center: investigation detail ------- */}
        <section className="min-h-0 overflow-y-auto pr-1">
          <InvestigationView
            result={investigation}
            loading={invLoading}
            error={invError}
            selectedAlert={selectedAlert}
            onSelectAlert={selectAlert}
            onOpenNode={openNode}
          />
        </section>

        {/* ------- right: graph + actions + memory ------- */}
        <aside className="hidden min-h-0 flex-col gap-3 overflow-y-auto xl:flex">
          <section className="rounded-lg border border-white/10 bg-slate-900/60 p-3">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                <Database className="h-3.5 w-3.5" /> Graph explorer
              </h2>
              <span className="font-mono text-[10px] text-slate-500">
                {graphCenter ?? "—"}
              </span>
            </div>
            <GraphExplorer
              data={graphData}
              loading={graphLoading}
              error={graphError}
              onNodeClick={openNode}
            />
            <p className="mt-2 text-[10px] text-slate-600">
              Click a node to re-center the traversal (1–4 hops, live FalkorDB
              query). Click node ids in the evidence paths to inspect them.
            </p>
          </section>

          <ActionPanel
            incidentId={investigation?.incident_id ?? null}
            actions={actions}
            onActionsChanged={setActions}
            analyst={analyst}
          />

          <MemoryPanel
            incidentId={investigation?.incident_id ?? null}
            memories={memories}
            analyst={analyst}
            onMemoryPosted={() =>
              void loadActionsAndMemories(investigation?.incident_id ?? null)
            }
          />
        </aside>
      </main>
    </div>
  );
}

import type { ReactNode } from "react";
import { AlertTriangle, Loader2, ShieldAlert } from "lucide-react";
import type { AlertSummary } from "@/lib/api";

// ---------------------------------------------------------------------------
// Small shared primitives
// ---------------------------------------------------------------------------

export const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-rose-500/15 text-rose-300 border-rose-500/40",
  high: "bg-orange-500/15 text-orange-300 border-orange-500/40",
  medium: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  low: "bg-sky-500/15 text-sky-300 border-sky-500/40",
};

export const LABEL_STYLES: Record<string, string> = {
  Alert: "bg-rose-500/15 text-rose-300 border-rose-500/40",
  Account: "bg-sky-500/15 text-sky-300 border-sky-500/40",
  Device: "bg-violet-500/15 text-violet-300 border-violet-500/40",
  IPAddress: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  Process: "bg-teal-500/15 text-teal-300 border-teal-500/40",
  Service: "bg-indigo-500/15 text-indigo-300 border-indigo-500/40",
  Incident: "bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/40",
  Evidence: "bg-zinc-500/15 text-zinc-300 border-zinc-500/40",
  Memory: "bg-yellow-500/15 text-yellow-300 border-yellow-500/40",
  Action: "bg-orange-500/15 text-orange-300 border-orange-500/40",
  Analyst: "bg-slate-500/15 text-slate-300 border-slate-500/40",
  Investigation: "bg-cyan-500/15 text-cyan-300 border-cyan-500/40",
};

export function Badge({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${className}`}
    >
      {children}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <Badge className={SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.low}>
      {severity}
    </Badge>
  );
}

export function Mono({ children }: { children: ReactNode }) {
  return <span className="font-mono text-[11px]">{children}</span>;
}

export function SectionCard({
  title,
  icon,
  right,
  children,
  className = "",
}: {
  title: string;
  icon?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-sm border border-white/10 bg-slate-900/60 ${className}`}
    >
      <header className="flex items-center justify-between gap-2 border-b border-white/10 px-3 py-2">
        <h2 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          {icon}
          {title}
        </h2>
        {right}
      </header>
      <div className="p-3">{children}</div>
    </section>
  );
}

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 rounded-sm border border-dashed border-white/10 p-8 text-sm text-slate-400">
      <Loader2 className="h-4 w-4 animate-spin" />
      {label}...
    </div>
  );
}

export function EmptyState({
  title,
  hint,
}: {
  title: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-sm border border-dashed border-white/10 p-8 text-center">
      <ShieldAlert className="h-6 w-6 text-slate-500" />
      <p className="text-sm font-medium text-slate-300">{title}</p>
      {hint && <p className="max-w-md text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-sm border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-300">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Incident queue row
// ---------------------------------------------------------------------------

export function QueueRow({
  alert,
  selected,
  onSelect,
}: {
  alert: AlertSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      aria-pressed={selected}
      className={`w-full border border-l-2 px-2.5 py-2 text-left transition ${
        selected
          ? "border-[var(--border)] border-l-[var(--accent)] bg-slate-800"
          : "border-transparent hover:border-[var(--border)] hover:bg-slate-900"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <SeverityBadge severity={alert.severity} />
        <span className="text-[10px] text-slate-500">
          {alert.ts ? alert.ts.replace("T", " ").replace("Z", "") : "no ts"}
        </span>
      </div>
      <p className="mt-1.5 line-clamp-2 text-xs font-medium text-slate-200">
        {alert.title}
      </p>
      <div className="mt-1.5 flex items-center justify-between">
        <span className="font-mono text-[10px] text-slate-500">{alert.id}</span>
        {alert.status === "grouped" ? (
          <Badge className="border-emerald-500/40 bg-emerald-500/10 text-emerald-300">
            grouped
          </Badge>
        ) : (
          <Badge className="border-slate-500/40 bg-slate-500/10 text-slate-400">
            new
          </Badge>
        )}
      </div>
    </button>
  );
}

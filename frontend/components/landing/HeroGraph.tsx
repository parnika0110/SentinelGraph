"use client";

import { useState } from "react";

type N = { id: string; x: number; y: number; label: string; kind: "alert" | "device" | "ext" | "user"; note: string; hot?: boolean };

const NODES: N[] = [
  { id: "a", x: 70, y: 130, label: "Alert A", kind: "alert", note: "Suspicious sign-in from an unrecognised external IP", hot: true },
  { id: "u", x: 175, y: 55, label: "user:ana.rios", kind: "user", note: "Account on the sign-in alert" },
  { id: "f", x: 240, y: 205, label: "dev:fin-ws-1042", kind: "device", note: "Observed on by Alert A", hot: true },
  { id: "p", x: 415, y: 205, label: "dev:srv-payments-01", kind: "device", note: "Connected to by fin-ws-1042", hot: true },
  { id: "b", x: 570, y: 120, label: "Alert B", kind: "alert", note: "C2 beacon candidates from the payments server", hot: true },
  { id: "i", x: 340, y: 335, label: "ip:external", kind: "ext", note: "Shared external IP only" },
  { id: "c", x: 545, y: 345, label: "Alert C", kind: "alert", note: "Excluded: shares only an external IP" },
];
const get = (id: string) => NODES.find((n) => n.id === id)!;
const MUTED: [string, string, boolean?][] = [["a", "u"], ["p", "i"], ["i", "c", true]];
const PATH = ["a", "f", "p", "b"];

export default function HeroGraph() {
  const [run, setRun] = useState(0);
  const [sel, setSel] = useState<N>(NODES[0]);
  const d = PATH.map((id, i) => `${i ? "L" : "M"}${get(id).x},${get(id).y}`).join(" ");

  return (
    <figure className="relative border border-[var(--border)] bg-[var(--surface)]">
      <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-2 font-mono text-[11px] text-[var(--text-2)]">
        <span>ILLUSTRATIVE SCENARIO · SYNTHETIC DATA</span>
        <button onClick={() => setRun((r) => r + 1)} className="border border-[var(--border)] px-2 py-0.5 text-[var(--accent)] transition hover:bg-[var(--surface-2)]">
          Trace evidence ↻
        </button>
      </div>
      <svg key={run} viewBox="0 0 640 400" role="img" aria-label="Evidence path from Alert A through two devices to Alert B; Alert C excluded" className="w-full" style={{ backgroundImage: "radial-gradient(#30332d 1px, transparent 1px)", backgroundSize: "20px 20px" }}>
        {MUTED.map(([s, t, dash], i) => (
          <line key={i} x1={get(s).x} y1={get(s).y} x2={get(t).x} y2={get(t).y} stroke="#5a5c54" strokeWidth="1.2" strokeDasharray={dash ? "4 4" : undefined} />
        ))}
        <path d={d} fill="none" stroke="#30332d" strokeWidth="2" />
        <path d={d} fill="none" stroke="#c5f36b" strokeWidth="2.2" className="sg-path" />
        {NODES.map((n, i) => {
          const on = sel.id === n.id;
          return (
            <g key={n.id} tabIndex={0} role="button" aria-label={`${n.label}: ${n.note}`} onClick={() => setSel(n)} onFocus={() => setSel(n)} onMouseEnter={() => setSel(n)} className="sg-in cursor-pointer outline-none" style={{ animationDelay: `${i * 120}ms` }}>
              {n.kind === "alert" ? (
                <rect x={n.x - 34} y={n.y - 16} width="68" height="32" fill="#181a17" stroke={n.hot ? "#c5f36b" : "#d9a441"} strokeWidth={on ? 2.4 : 1.2} />
              ) : (
                <circle cx={n.x} cy={n.y} r={on ? 11 : 9} fill="#20221e" stroke={n.hot ? "#c5f36b" : "#7a7c72"} strokeWidth="1.4" />
              )}
              <text x={n.x} y={n.kind === "alert" ? n.y + 4 : n.y + 26} textAnchor="middle" fill="#f0f0e8" fontSize="10.5" fontFamily="var(--font-geist-mono)">{n.label}</text>
            </g>
          );
        })}
      </svg>
      <figcaption className="grid gap-3 border-t border-[var(--border)] p-4 text-sm sm:grid-cols-[1fr_auto]">
        <div aria-live="polite">
          <p className="font-mono text-xs text-[var(--accent)]">{sel.label}</p>
          <p className="mt-1 text-[var(--text-2)]">{sel.note}</p>
        </div>
        <ul className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-[var(--text-2)] sm:flex-col">
          <li><span className="mr-1.5 inline-block h-0.5 w-4 bg-[var(--accent)] align-middle" />Evidence path</li>
          <li><span className="mr-1.5 inline-block h-0.5 w-4 bg-[#5a5c54] align-middle" />Other relationship</li>
          <li><span className="mr-1.5 inline-block h-2 w-2 border border-[#d9a441] align-middle" />Excluded alert</li>
        </ul>
      </figcaption>
    </figure>
  );
}

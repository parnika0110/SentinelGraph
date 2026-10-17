import Link from "next/link";
import { Activity, Database, Filter, Home, ShieldCheck } from "lucide-react";

const ITEMS = [
  { href: "#queue", label: "Alert queue", Icon: Filter },
  { href: "#investigation", label: "Investigation", Icon: Activity },
  { href: "#graph", label: "Graph explorer", Icon: Database },
  { href: "#review", label: "Review & memory", Icon: ShieldCheck },
];

export function Mark() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M4 18 10 7l5 6 5-9" stroke="#c5f36b" strokeWidth="1.8" />
      {[[4, 18], [10, 7], [15, 13], [20, 4]].map(([x, y]) => (
        <circle key={x} cx={x} cy={y} r="2.2" fill="#10110f" stroke="#f0f0e8" strokeWidth="1.4" />
      ))}
    </svg>
  );
}

/** Slim left rail (lg+). Items are in-page anchors: the workspace is one screen. */
export default function Rail() {
  return (
    <nav aria-label="Workspace" className="hidden w-14 shrink-0 flex-col items-center gap-1 border-r border-[var(--border)] bg-[var(--bg)] py-3 lg:flex">
      <Link href="/" aria-label="SentinelGraph home" title="Home" className="mb-3 flex h-9 w-9 items-center justify-center hover:bg-[var(--surface)]">
        <Mark />
      </Link>
      {ITEMS.map(({ href, label, Icon }) => (
        <a key={href} href={href} aria-label={label} title={label} className="group relative flex h-9 w-9 items-center justify-center text-[var(--text-2)] transition hover:bg-[var(--surface)] hover:text-[var(--text)] focus-visible:text-[var(--accent)]">
          <Icon className="h-4 w-4" />
        </a>
      ))}
      <Link href="/" aria-label="Back to site" title="Back to site" className="mt-auto flex h-9 w-9 items-center justify-center text-[var(--text-2)] hover:text-[var(--text)]">
        <Home className="h-4 w-4" />
      </Link>
    </nav>
  );
}

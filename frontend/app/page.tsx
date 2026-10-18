import Link from "next/link";
import HeroGraph from "@/components/landing/HeroGraph";

const REPO = "https://github.com/parnika0110/SentinelGraph";
const label = "font-mono text-[11px] uppercase tracking-[0.16em] text-[var(--text-2)]";
const btn = "inline-flex items-center px-5 py-3 text-sm font-medium transition";

function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
        <path d="M4 18 10 7l5 6 5-9" stroke="#c5f36b" strokeWidth="1.8" />
        {[[4, 18], [10, 7], [15, 13], [20, 4]].map(([x, y]) => <circle key={x} cx={x} cy={y} r="2.2" fill="#10110f" stroke="#f0f0e8" strokeWidth="1.4" />)}
      </svg>
      <span className="font-serif text-xl tracking-tight">SentinelGraph</span>
    </span>
  );
}

const STEPS = [
  ["01", "Connect", "Relate alerts through shared entities and graph relationships."],
  ["02", "Investigate", "Trace multi-hop paths and examine the supporting evidence."],
  ["03", "Recall", "Retrieve relevant historical investigations and their context."],
  ["04", "Review", "Evaluate proposed response actions and retain analyst control."],
];
const STACK = [
  ["Alerts", "Synthetic demo alerts and entities"],
  ["FalkorDB", "Graph storage and bounded multi-hop traversal"],
  ["FastAPI", "Investigation service: correlation, ranking, memory retrieval"],
  ["Workspace", "Analyst UI: evidence paths, graph, history"],
  ["Review", "Human approval of simulated actions"],
];
const TRUST = [
  ["Inspectable evidence", "Each grouping cites the concrete node-and-relationship chain behind it."],
  ["Related vs. unrelated", "Excluded alerts are listed with the reason they were left out."],
  ["Historical context", "Prior incidents are recalled from graph memory and marked as unverified leads."],
  ["Analyst in control", "Actions are proposals. Nothing runs without an explicit approve or reject."],
];

export default function Landing() {
  return (
    <main className="min-h-screen bg-[var(--bg)] text-[var(--text)]">
      <header className="sticky top-0 z-20 border-b border-[var(--border)] bg-[var(--bg)]/95">
        <nav className="mx-auto flex max-w-7xl items-center justify-between px-5 py-3.5" aria-label="Primary">
          <Link href="/" aria-label="SentinelGraph home"><Logo /></Link>
          <div className="hidden items-center gap-7 text-sm text-[var(--text-2)] md:flex">
            <a href="#product" className="hover:text-[var(--text)]">Product</a>
            <a href="#how" className="hover:text-[var(--text)]">How it works</a>
            <a href="#architecture" className="hover:text-[var(--text)]">Architecture</a>
            <a href={REPO} className="hover:text-[var(--text)]">GitHub</a>
            <Link href="/app" className={`${btn} bg-[var(--accent)] py-2 text-[var(--bg)] hover:brightness-110`}>Open workspace</Link>
          </div>
          <details className="relative md:hidden">
            <summary className="cursor-pointer list-none border border-[var(--border)] px-3 py-1.5 text-sm">Menu</summary>
            <div className="absolute right-0 mt-2 flex w-52 flex-col gap-3 border border-[var(--border)] bg-[var(--surface)] p-4 text-sm">
              <a href="#product">Product</a><a href="#how">How it works</a><a href="#architecture">Architecture</a><a href={REPO}>GitHub</a>
              <Link href="/app" className="text-[var(--accent)]">Open workspace →</Link>
            </div>
          </details>
        </nav>
      </header>

      <section className="mx-auto grid max-w-7xl gap-12 px-5 pb-20 pt-16 lg:grid-cols-[45fr_55fr] lg:items-center lg:pt-24">
        <div>
          <p className={label}>Graph-powered security investigation</p>
          <h1 className="mt-6 font-serif text-5xl leading-[1.02] tracking-tight sm:text-6xl xl:text-7xl">
            Every alert is a clue.<br /><em className="text-[var(--accent)]">Find the connections.</em>
          </h1>
          <p className="mt-6 max-w-lg text-lg leading-relaxed text-[var(--text-2)]">
            SentinelGraph connects alerts, entities, and historical incidents into explainable evidence paths, so analysts can understand what happened, why it matters, and what to review next.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/app" className={`${btn} bg-[var(--accent)] text-[var(--bg)] hover:brightness-110`}>Open investigation workspace</Link>
            <a href="#how" className={`${btn} border border-[var(--border)] hover:bg-[var(--surface)]`}>Explore how it works</a>
          </div>
          <p className="mt-8 font-mono text-xs text-[var(--text-2)]">Graph-powered correlation · Explainable evidence · Analyst-controlled actions</p>
        </div>
        <HeroGraph />
      </section>

      <section id="how" className="border-t border-[var(--border)]">
        <div className="mx-auto max-w-7xl px-5 py-24">
          <p className={label}>How it works</p>
          <h2 className="mt-4 max-w-2xl font-serif text-4xl leading-tight sm:text-5xl">From isolated signals to an explainable incident.</h2>
          <ol className="mt-14 grid border-t border-[var(--border)] md:grid-cols-4">
            {STEPS.map(([n, t, d]) => (
              <li key={n} className="border-b border-[var(--border)] py-8 md:border-b-0 md:border-r md:px-6 md:first:pl-0 md:last:border-r-0">
                <span className="font-mono text-xs text-[var(--accent)]">{n}</span>
                <h3 className="mt-3 font-serif text-2xl">{t}</h3>
                <p className="mt-2 text-sm leading-relaxed text-[var(--text-2)]">{d}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section id="product" className="border-t border-[var(--border)] bg-[var(--surface)]">
        <div className="mx-auto grid max-w-7xl gap-12 px-5 py-24 lg:grid-cols-2">
          <div>
            <p className={label}>The workspace</p>
            <h2 className="mt-4 font-serif text-4xl leading-tight">A queue, a graph, and the reasons behind both.</h2>
            <p className="mt-5 leading-relaxed text-[var(--text-2)]">Pick an alert, run the investigation, and read the result from live graph queries: grouped alerts with their evidence paths, excluded alerts with reasons, recalled historical incidents, and response actions awaiting your decision.</p>
            <Link href="/app" className={`${btn} mt-8 bg-[var(--accent)] text-[var(--bg)] hover:brightness-110`}>Open the workspace →</Link>
          </div>
          <div className="border border-[var(--border)] bg-[var(--bg)] font-mono text-xs">
            <div className="border-b border-[var(--border)] px-4 py-2 text-[var(--text-2)]">ILLUSTRATIVE · SYNTHETIC ALERT QUEUE</div>
            {[["high", "Suspicious sign-in", "grouped", "#d9a441"], ["high", "C2 beacon candidates", "grouped", "#d9a441"], ["medium", "Malware on marketing laptop", "excluded", "#c9b45a"]].map(([s, t, st, c]) => (
              <div key={t} className="flex items-center gap-3 border-b border-[var(--border)] px-4 py-3 last:border-0">
                <span className="h-2 w-2" style={{ background: c }} /><span className="w-14 text-[var(--text-2)]">{s}</span>
                <span className="flex-1 truncate font-sans text-sm">{t}</span><span className="text-[var(--text-2)]">{st}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="architecture" className="border-t border-[var(--border)]">
        <div className="mx-auto max-w-7xl px-5 py-24">
          <p className={label}>Architecture</p>
          <h2 className="mt-4 max-w-2xl font-serif text-4xl leading-tight sm:text-5xl">The graph is the reasoning layer.</h2>
          <p className="mt-5 max-w-2xl leading-relaxed text-[var(--text-2)]">FalkorDB holds alerts, entities, findings and incident memory. Every fact in the UI comes from a parameterized Cypher query, so relationships are retrieved, not guessed.</p>
          <ol className="mt-12 grid gap-px border border-[var(--border)] bg-[var(--border)] md:grid-cols-5">
            {STACK.map(([t, d], i) => (
              <li key={t} className="bg-[var(--bg)] p-5">
                <span className="font-mono text-xs text-[var(--accent)]">{String(i + 1).padStart(2, "0")} →</span>
                <h3 className="mt-3 font-mono text-sm">{t}</h3>
                <p className="mt-2 text-sm text-[var(--text-2)]">{d}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="border-t border-[var(--border)] bg-[var(--surface)]">
        <div className="mx-auto max-w-7xl px-5 py-24">
          <p className={label}>Trust and control</p>
          <h2 className="mt-4 font-serif text-4xl sm:text-5xl">Explainable by construction.</h2>
          <dl className="mt-12 grid gap-10 sm:grid-cols-2">
            {TRUST.map(([t, d]) => (
              <div key={t} className="border-l border-[var(--accent)] pl-5"><dt className="font-medium">{t}</dt><dd className="mt-1.5 text-sm leading-relaxed text-[var(--text-2)]">{d}</dd></div>
            ))}
          </dl>
          <p className="mt-12 text-sm text-[var(--text-2)]">This is a demonstration built on synthetic data. It does not process real telemetry and does not execute remediation.</p>
        </div>
      </section>

      <footer className="border-t border-[var(--border)]">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-6 px-5 py-10">
          <div><Logo /><p className="mt-3 max-w-xs text-sm text-[var(--text-2)]">Graph-powered incident investigation. Demo on synthetic data.</p></div>
          <div className="flex gap-6 text-sm"><a href={REPO} className="hover:text-[var(--accent)]">GitHub</a><Link href="/app" className="hover:text-[var(--accent)]">Open workspace</Link></div>
          <p className="w-full font-mono text-[11px] text-[var(--text-2)]">Built with Next.js, FastAPI and FalkorDB.</p>
        </div>
      </footer>
    </main>
  );
}

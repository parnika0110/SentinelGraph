# SentinelGraph — frontend

The analyst dashboard: incident queue, investigation detail (observed facts vs
hypotheses, evidence paths, timeline), interactive FalkorDB graph explorer,
historical-memory panel, and approval-gated response actions.

- **Stack:** Next.js 16 · React 19 · TypeScript · Tailwind CSS v4 ·
  [@xyflow/react](https://reactflow.dev) · lucide-react
- **API client:** [lib/api.ts](lib/api.ts) (typed; every panel fetches from the
  backend — no hardcoded investigation results)
- **Tests:** `npm test` (vitest + jsdom + Testing Library, 19 tests)

## Run

```bash
npm install
npm run dev                    # http://localhost:3000 (expects backend on :8000)
# landing page at `/`; investigation workspace at `/app`
# production:
npm run build && npm run start -- --port 3000
```

Backend URL comes from `NEXT_PUBLIC_API_URL` (default
`http://localhost:8000` — see the root `.env.example`).

See the [repository root README](../README.md) for the full architecture,
graph schema and setup instructions.

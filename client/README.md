# Callwire web

React + TypeScript (Vite) front end for the Callwire engine.

```bash
npm install
cp .env.example .env     # VITE_API_TARGET = where the engine runs (default http://localhost:8000)
npm run dev              # http://localhost:5173
npm run build            # typecheck + production build into dist/
```

In dev, Vite proxies `/v1` and `/stream` to `VITE_API_TARGET`, so there are no CORS issues. For a production build served from another origin, set `VITE_API_BASE=https://your-engine` before building.

## Pages (hash routes)

| Route | Page | Talks to |
|---|---|---|
| `#/` | **Wire**: card grid of briefs, filter by company or quarter, `new` flag on live arrivals | `GET /v1/briefs`, `WS /stream/briefs` |
| `#/call/{id}` | **Reader**: TL;DR, then Overview / Numbers / Q&A / Risks tabs, Markdown copy + download | `GET /v1/briefs/{id}`, `/markdown` |
| `#/replay` | **Replay**: look back N days, plus a live pipeline activity log | `POST /v1/replay`, `GET /v1/replay/{job_id}`, `GET /v1/activity` |
| `#/stream` | **Stream**: socket URLs for other apps, connection test, example payload, JS/Python snippets | `/stream/briefs`, `/stream/activity` |

## Layout

```
src/
  App.tsx            masthead + hash router; owns the live list so the socket stays open
  lib/               api.ts (fetch + socket URLs), shape.ts (tolerant coercion), format.ts, types.ts
  hooks/useWire.ts   list + live updates, per-brief cache
  views/             Wire, Reader, Replay, Stream
  ui/                Blocks.tsx (bullets, metrics table, Q&A, tone), useCopy.ts
  styles.css         dark amber theme; follows the OS light/dark setting
```

The summary text comes from an LLM, so `lib/shape.ts` coerces every list field (string, array or object) into a safe shape before it's rendered.

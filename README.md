# Callwire

**Earnings-call summaries for Indian listed companies, delivered as the transcripts are filed.**

Callwire polls the NSE and BSE announcement feeds, spots concall *transcripts*, downloads the PDF, cleans the text, produces a grounded structured summary with an LLM, and pushes it to a web UI and to any other service over a WebSocket.

> Built for the Finosauras Tech Software Engineer Intern take-home.

```
ingest  ->  reader  ->  digest  ->  gateway
watch NSE/BSE   PDF -> clean   map-reduce LLM    REST + WebSocket
download PDF    text           summary + checks   + web UI
```

## Contents
[Quick start](#quick-start) · [Configuration](#configuration) · [How it works](#how-it-works) · [Output schema](#output-schema) · [API and sockets](#api-and-sockets) · [Design decisions](#design-decisions) · [Which companies](#which-companies) · [Assignment checklist](#assignment-checklist) · [Known limitations](#known-limitations) · [Troubleshooting](#troubleshooting) · [Project layout](#project-layout) · [Testing](#testing) · [With more time](#with-more-time)

## Quick start

Needs Python 3.10+ and Node 18+ (Node only for the UI).

```bash
# 1. add your LLM key (never commit this file)
cp engine/.env.example engine/.env        # Windows: copy engine\.env.example engine\.env
#    then set LLM_API_KEY=<your key> in engine/.env

# 2. one command: engine + watcher + sockets + UI
python run.py
```

`run.py` creates a virtualenv, installs Python and npm packages on first run, starts the engine on <http://localhost:8000> and the UI on <http://localhost:5173>, opens your browser, and stops both on **Ctrl+C**. It refuses to start without an API key, because Callwire never fabricates summaries.

| Command | Result |
|---|---|
| `python run.py` | Engine + React UI |
| `python run.py --api-only` | Engine only; a built-in page is served at http://localhost:8000 |
| `python run.py --no-browser` | Don't open a browser tab |

Any OpenAI-compatible provider works, including free tiers: [Groq](https://console.groq.com), Google Gemini, OpenRouter.

### Saving sample outputs

Once some summaries have finished, run from `engine/`:

```bash
cd engine
python tools/dump_samples.py
```

Each stored brief becomes `engine/samples/<Company>_<Quarter>/` with `transcript.txt` (cleaned text from the PDF), `summary.json` and `summary.md`. To get older calls quickly, use **Replay** in the UI (or `POST /v1/replay?days=45`) first.

## Configuration

Everything lives in `engine/.env` (see `.env.example`).

| Variable | Default | Meaning |
|---|---|---|
| `LLM_API_KEY` | *(required)* | Provider API key |
| `LLM_BASE_URL` | Groq endpoint | Any OpenAI-compatible base URL |
| `LLM_MODEL` | `openai/gpt-oss-120b` | Model id |
| `WATCH_MODE` | auto | `watchlist` = only your companies, `all` = every transcript. Auto = `watchlist` if `WATCHLIST`/`SYMBOLS` is set, else `all` |
| `WATCHLIST` | empty | Comma-separated company-name fragments, e.g. `"HDFC Bank,Tata Motors"` |
| `SYMBOLS` | empty | Optional NSE symbols, queried one by one |
| `MAX_SUMMARIES_PER_DAY` | `40` in `all` mode, else `0` (unlimited) | Daily cap, a cost safety valve |
| `POLL_SECONDS` | `120` | Delay between exchange checks |
| `LOOKBACK_DAYS` | `3` (`45` in the example file) | How far back each check looks |
| `SOURCES` | `nse,bse` | Use `nse` to skip BSE |
| `LLM_TPM` | `7000` | Tokens-per-minute budget the client paces itself under |
| `LLM_MAX_OUT` | `1200` | Max output tokens per call |
| `CHUNK_CHARS` | `4000` | Transcript chunk size |
| `DB_PATH` | `data/callwire.db` | SQLite file |

## How it works

```mermaid
flowchart LR
    A[NSE / BSE feeds] -->|every POLL_SECONDS| B[ingest<br/>filter, dedupe, download]
    B --> C[reader<br/>PDF to clean text]
    C --> D[digest<br/>chunk, map, merge, verify]
    D --> E[(SQLite)]
    D --> F[/stream/briefs]
    E --> G[REST /v1]
    G --> H[React UI]
    F --> H
    F --> I[Any other service]
```

**1. Ingest** (`engine/ingest/`)
- `session.py`: browser-like sessions with warm-up cookies, a minimum gap between requests, exponential-backoff retries, and a fresh session on 401/429/5xx. A 403 (firewall block) is reported once rather than retried.
- `exchanges.py`: NSE and BSE fetchers. A filing counts as a transcript if its text says "transcript"; intimations and audio-only filings don't, so they're skipped.
- `scanner.py`: the polling loop. **Three dedupe layers:** URL already handled; normalised company name + call date (so the NSE and BSE copies of one call match); SHA-256 of the extracted text. One exchange failing never stops the other.

**2. Reader** (`engine/reader/pdf_text.py`)
- PyMuPDF with reading-order sort for multi-column pages.
- Headers/footers are removed by repetition across pages (speaker lines are protected), page numbers dropped, wrapped lines re-joined, speaker turns kept apart.
- Per-page OCR fallback for image-only pages (needs Tesseract installed).
- Call date and quarter are detected from the transcript text; the filing date is stored separately.

**3. Digest** (`engine/digest/`)
- `mapreduce.py`: the transcript is cut into ~4,000-character chunks; each is read by the LLM (**map**); partial results are merged in rounds sized to the token budget (**reduce**).
- Prompts allow only information in the text. Every key metric carries `entity`, `period` and a verbatim `quote`.
- **Verified in code:** each metric is tagged `full` (quote found in the transcript *and* the number is inside it), `number_only` (number exists somewhere, quote doesn't match, so check by hand) or `no`. The UI shows these as *verified / number only / unverified*.
- `llm_client.py` paces requests under the provider's token limit, retries, and repairs truncated JSON. Chunk results are cached on disk so a failed run resumes. Management tone (positive / neutral / cautious / negative) is scored with a reason.

**4. Gateway** (`engine/gateway/`, `client/`)
- FastAPI serves the REST API and two WebSocket feeds. The React UI lists briefs, opens each one in a reader, and shows new ones as they land.

## Output schema

```jsonc
{
  "company": "string",
  "scrip_code": "string | null",     // BSE code when the source is BSE
  "nse_symbol": "string | null",     // NSE symbol when the source is NSE
  "quarter": "e.g. Q2 FY27",
  "call_date": "YYYY-MM-DD",         // read from the transcript, falls back to filing date
  "filing_date": "YYYY-MM-DD",
  "source": "NSE | BSE",
  "source_url": "string",
  "chunks_processed": 0,
  "tldr": ["3-5 short lines"],
  "management_commentary": ["..."],
  "guidance": ["entity + period + target"],
  "segment_performance": [{ "segment": "...", "notes": "..." }],
  "key_metrics": [{
    "metric": "...", "entity": "...", "period": "...", "value": "...",
    "context": "...", "quote": "verbatim from the call",
    "verified": "full | number_only | no"
  }],
  "notable_qa": [{ "question": "...", "answer": "...", "asked_by": "...", "answered_by": "..." }],
  "risks": ["..."],
  "tone": { "label": "positive | neutral | cautious | negative", "reason": "..." }
}
```

**Additions to the assignment's example schema, and why:** `filing_date` (filing and call dates differ); `entity` and `period` on metrics (a segment's number is never mistaken for a consolidated one); `quote` and `verified` (back the no-hallucination rule with evidence); `answered_by` (who actually answered); `tone` (bonus sentiment scoring); `chunks_processed` (transparency).

## API and sockets

| Endpoint | Purpose |
|---|---|
| `GET /v1/briefs` | List of briefs (id, company, quarter, call date, source) |
| `GET /v1/briefs/{id}` | Full brief as JSON |
| `GET /v1/briefs/{id}/markdown` | The same brief as Markdown |
| `POST /v1/replay?days=N` | Start a background historical replay; returns a job id immediately |
| `GET /v1/replay/{job_id}` | Get replay status, progress, and errors |
| `GET /v1/activity?since=N` | Recent pipeline events, including raw LLM replies |
| `WS /stream/briefs` | One JSON message per newly finished brief |
| `WS /stream/activity` | Every pipeline step and LLM reply; recent history replayed on connect |
| `GET /` and `GET /activity` | Built-in pages (briefs, live activity) served by the engine itself |

**Subscribe from any app:**

```python
import asyncio, json, websockets

async def listen():
    async with websockets.connect("ws://localhost:8000/stream/briefs") as ws:
        async for msg in ws:
            brief = json.loads(msg)
            print("NEW:", brief["company"], brief["quarter"], brief["tldr"])

asyncio.run(listen())
```

`/stream/briefs` only sends briefs finished *after* you connect; call `GET /v1/briefs` first to catch up. The sockets have no authentication, so don't expose them publicly as they are.

## Design decisions

- **Map-reduce over one giant prompt.** Long transcripts don't fit small context windows, and per-chunk extraction with verbatim quotes keeps every claim traceable.
- **Verify in code, not only in prompts.** Asking a model not to hallucinate isn't enough, so each number is checked against the source text and flagged when unsupported.
- **Provider-agnostic.** Any OpenAI-compatible endpoint works; no provider SDK.
- **No mock mode.** Without a real key the engine refuses to start instead of producing placeholder summaries.
- **Polling, not push.** The exchanges offer no push feed, so latency is at most `POLL_SECONDS` plus processing time.
- **Resilience over cleverness.** Per-item failures are logged and retried next poll, one exchange failing doesn't stop the other, chunk results are cached, and a stop flag lets worker threads exit on Ctrl+C.
- **SQLite.** Zero setup, enough for this scale.
- **Four separate stages** (`ingest`, `reader`, `digest`, `gateway`) that only talk through plain dicts, so each can be tested or swapped alone.

## Which companies

`WATCH_MODE` chooses the scope:

| Mode | Processes | Best for |
|---|---|---|
| `watchlist` | Only companies in `WATCHLIST` / `SYMBOLS` | The assignment's 5-10 company scope; predictable cost |
| `all` | Every transcript found, up to `MAX_SUMMARIES_PER_DAY` | Broad coverage once you have budget |

The example config tracks six companies across sectors. Entries are name fragments matched against the filing's company name (so `Tata Motors` also matches `Tata Motors Passenger Vehicles Limited`).

| In `WATCHLIST` | Sector |
|---|---|
| `HDFC Bank` | Banking |
| `Tata Motors` | Automobiles (passenger vehicles + JLR) |
| `Infosys` | IT services |
| `Sun Pharma` | Pharmaceuticals |
| `Reliance` | Conglomerate (energy, telecom, retail) |
| `Larsen` | Engineering and construction |

**Cost.** Scanning the feeds is cheap and always covers every company. The LLM is the real cost: roughly 15-20 calls per transcript (on the order of 45k input and 15k output tokens, varying with length). On a free tier the limit is time instead of money: about 6-10 minutes per transcript. `all` mode is capped by `MAX_SUMMARIES_PER_DAY`; newest filings go first and the rest wait for the next day.

## Assignment checklist

| Requirement | Status |
|---|---|
| Watch NSE and BSE, filter transcripts, download | NSE works. BSE is implemented but blocked by its firewall (HTTP 403) in my environment, so unverified |
| Headers/sessions, retries, rate limiting, dedupe | Done (three dedupe layers) |
| Clean text, headers/footers, speaker labels | Done |
| Parse XBRL (optional) | Not done; metadata comes from the announcement feed and the transcript text |
| OCR fallback (bonus) | Implemented, needs Tesseract, untested on real scanned PDFs |
| TL;DR, commentary, guidance, segments, numbers, Q&A, risks | Done |
| JSON **and** Markdown output | Done |
| No hallucination | Grounded prompts + code-level verification; `number only` / `unverified` rows need a human look |
| Long transcripts | Chunking + map-reduce |
| Real-time, unattended | Polling loop inside the engine |
| Minimal UI | React app (wire, reader, replay, stream pages) |
| WebSocket feed | `/stream/briefs` and `/stream/activity` |
| One command | `python run.py` |
| README, limitations, "more time" | This file |
| Sample outputs for 3+ companies | `engine/samples/` (3 with transcript + JSON + Markdown, 1 without transcript) |
| Bonus: caching, tone, backfill | Done (chunk cache, tone, `POST /v1/replay`) |
| Bonus: audio-only filings | Skipped rather than tracked |

## Known limitations

- **BSE is blocked** by its firewall (403) in my environment even with a warmed session, so only NSE currently supplies filings. NSE carries the same concall filings.
- **Free-tier LLM limits.** Transcripts are processed one after another and daily token caps can pause a long replay. Cached chunks are reused on retry.
- **Merges keep the top items.** To fit the token budget, intermediate merges keep about 3 items per list, so some detail can be lost on very long calls.
- **Call date** is the first date-like string in the transcript's opening; it falls back to the filing date.
- **Verification proves a quote exists, not that it was understood correctly.** Check `number only` / `unverified` rows by hand.
- Latency is `POLL_SECONDS` plus 5-10 minutes of processing. XBRL isn't parsed. No auth on the API or sockets. Processing is in-process with no job queue.
- Replay runs in the background; poll `GET /v1/replay/{job_id}` for progress and completion.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `LLM_API_KEY is not set` | Create `engine/.env` from `.env.example` and add a real key |
| LLM `404 Not Found` | The model id doesn't exist for your key: `curl -s $LLM_BASE_URL/models -H "Authorization: Bearer $LLM_API_KEY"` |
| LLM `413` / rate-limit warnings | Free-tier token limit. Lower `LLM_TPM`, `LLM_MAX_OUT` or `CHUNK_CHARS`, or use a smaller model |
| `pull_bse failed: BSE API 403` | Known firewall block. Set `SOURCES=nse` to silence it |
| List is empty but the log shows LLM calls | A transcript takes minutes; it appears automatically when done. Watch the Replay page or `/activity` |
| Older companies never appear | Raise `LOOKBACK_DAYS`, or use Replay / `POST /v1/replay?days=45` |
| `bash: Bank,Tata: command not found` | Quote the value in `.env`: `WATCHLIST="HDFC Bank,Tata Motors"` |
| A `node` process lingers after Ctrl+C (Windows) | `taskkill /F /IM node.exe` |

## Project layout

```
.
├── run.py                one command: engine + UI
├── engine/               Python backend
│   ├── main.py           starts the API server (and the watcher)
│   ├── settings.py       configuration from .env
│   ├── flow.py           one filing: read -> digest -> store
│   ├── store.py          SQLite storage
│   ├── ingest/           Stage 1: session.py, exchanges.py (NSE/BSE), scanner.py (loop, dedupe)
│   ├── reader/           Stage 2: pdf_text.py (PDF -> text, quarter, call date)
│   ├── digest/           Stage 3: events.py, llm_client.py, mapreduce.py, render.py
│   ├── gateway/          Stage 4: app.py (REST + sockets), pages/ (built-in HTML)
│   ├── tools/            dump_samples.py
│   ├── tests/            offline tests
│   └── samples/          real outputs (transcript, JSON, Markdown)
└── client/               React + TypeScript UI (Vite)
```

## Testing

```bash
cd engine
.venv/bin/python -m pytest -q # offline: no network, no API key
cd ../client
npm run build                # typecheck + production build
```

The only test double is the LLM network call; production code has no mock path.

## With more time

- Parse the XBRL attachments for exact company, scrip code, event date and quarter.
- A durable job queue with parallel workers so a busy results day doesn't back up.
- Span-level citations linking every claim to its place in the transcript.
- A hand-written evaluation set to compare models on summary accuracy.
- A compliant data source for BSE; authentication on the API and sockets; Docker packaging.
- Track audio-only filings and process them when the transcript follows.
- Quarter-over-quarter tone and guidance tracking per company.

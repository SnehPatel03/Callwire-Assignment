"""Stage 4: REST API, WebSocket feeds and the built-in fallback pages.

REST        GET  /v1/briefs                  list
            GET  /v1/briefs/{id}             one brief (JSON)
            GET  /v1/briefs/{id}/markdown    one brief (Markdown)
            POST /v1/replay?days=N           pull older transcripts
            GET  /v1/activity?since=N        recent pipeline events
WebSocket   /stream/briefs                   each finished brief, pushed live
            /stream/activity                 every pipeline step + raw LLM reply
Pages       /  and  /activity
"""
import asyncio
import collections
import itertools
import json
import logging
import pathlib
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

import flow
import settings
import store
from digest import events as digest_events
from ingest import exchanges, scanner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
PAGES = pathlib.Path(__file__).parent / "pages"


class Broadcaster:
    """The set of connected WebSocket clients for one feed."""

    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def send_all(self, message: dict) -> None:
        payload = json.dumps(message)
        for ws in list(self.clients):
            try:
                await ws.send_text(payload)
            except Exception:
                self.clients.discard(ws)


briefs_feed = Broadcaster()
activity_feed = Broadcaster()
recent_events: collections.deque = collections.deque(maxlen=500)
_event_seq = itertools.count(1)
replay_state: dict = {"id": None, "status": "idle", "days": None, "found": 0, "processed": 0, "failed": 0, "current": None, "error": None}
replay_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init()
    digest_events.shutdown.clear()
    watching = not getattr(app.state, "no_watcher", False)  # tests switch the watcher off

    if watching:
        if not settings.LLM_API_KEY:
            raise RuntimeError("LLM_API_KEY is not set. Put a real key in .env - the pipeline never fabricates summaries.")
        slog = logging.getLogger("gateway")
        slog.info("WATCH_MODE=%s watchlist=%s symbols=%s daily_cap=%s", settings.WATCH_MODE,
                  settings.WATCHLIST or "-", settings.SYMBOLS or "-", settings.MAX_SUMMARIES_PER_DAY or "unlimited")
        if settings.WATCH_MODE == "all":
            slog.warning("WATCH_MODE=all: every concall transcript will be summarised (LLM cost grows with filings; cap=%s/day)",
                         settings.MAX_SUMMARIES_PER_DAY or "none")

    loop = asyncio.get_running_loop()

    def on_event(event: dict) -> None:  # called from worker threads
        event["seq"] = next(_event_seq)
        recent_events.append(event)
        loop.call_soon_threadsafe(lambda: asyncio.ensure_future(activity_feed.send_all(event)))

    digest_events.listeners.append(on_event)
    task = asyncio.create_task(scanner.run_forever(flow.make_handler(briefs_feed.send_all))) if watching else None
    yield
    digest_events.shutdown.set()  # let worker threads exit so the process can stop
    digest_events.listeners.remove(on_event)
    if task:
        task.cancel()


app = FastAPI(title="Callwire", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- pages ------------------------------------------------------------------------
@app.get("/")
def home_page():
    return FileResponse(PAGES / "home.html")


@app.get("/activity")
def activity_page():
    return FileResponse(PAGES / "activity.html")


# ---- REST -------------------------------------------------------------------------
@app.get("/v1/briefs")
def list_briefs():
    return store.list_briefs()


@app.get("/v1/briefs/{brief_id}")
def get_brief(brief_id: int):
    row = store.get_brief(brief_id)
    if not row:
        raise HTTPException(404)
    try:
        summary = json.loads(row["payload"])
    except (json.JSONDecodeError, TypeError):
        summary = {}
    if not isinstance(summary, dict):
        summary = {}
    # The stored JSON wins; the table columns fill any gaps.
    return {
        **summary,
        "id": row["id"],
        "company": summary.get("company") or row["company"],
        "quarter": summary.get("quarter") or row["quarter"],
        "call_date": summary.get("call_date") or row["call_date"],
        "source": summary.get("source") or row["source"],
        "source_url": summary.get("source_url") or row["url"],
    }


@app.get("/v1/briefs/{brief_id}/markdown", response_class=PlainTextResponse)
def get_brief_markdown(brief_id: int):
    row = store.get_brief(brief_id)
    if not row:
        raise HTTPException(404)
    return row["markdown"]


@app.get("/v1/activity")
def activity(since: int = 0):
    return [e for e in recent_events if e["seq"] > since]


@app.post("/v1/replay")
async def replay(days: int = Query(default=30, ge=1, le=365)):
    """Start a replay in the background; progress is available through status and activity."""
    global replay_task
    if replay_task and not replay_task.done():
        raise HTTPException(409, "A replay is already running")

    job_id = uuid.uuid4().hex
    replay_state.update(id=job_id, status="scanning", days=days, found=0, processed=0, failed=0, current=None, error=None)
    digest_events.emit("replay_started", replay_id=job_id, days=days)
    replay_task = asyncio.create_task(_run_replay(job_id, days))
    return dict(replay_state)


@app.get("/v1/replay/{job_id}")
def get_replay(job_id: str):
    if replay_state.get("id") != job_id:
        raise HTTPException(404, "Replay not found")
    return dict(replay_state)


async def _run_replay(job_id: str, days: int) -> None:
    try:
        items = await asyncio.to_thread(scanner.scan_once, days)
        if replay_state.get("id") != job_id:
            return
        replay_state.update(status="running", found=len(items))
        digest_events.emit("replay_scanned", replay_id=job_id, found=len(items), days=days)
        handle = flow.make_handler(briefs_feed.send_all)
        for index, item in enumerate(items, start=1):
            if replay_state.get("id") != job_id:
                return
            company = item.get("company", "Unknown company")
            replay_state["current"] = company
            digest_events.emit("replay_item_started", replay_id=job_id, company=company, index=index, total=len(items))
            try:
                pdf = await asyncio.to_thread(exchanges.fetch_pdf, item)
                await handle(item, pdf)
                store.mark_url_seen(item["url"])
                replay_state["processed"] += 1
                digest_events.emit("replay_item_done", replay_id=job_id, company=company,
                                   processed=replay_state["processed"], total=len(items))
            except Exception as exc:
                replay_state["failed"] += 1
                logging.getLogger("replay").exception("%s: %s", item["url"], exc)
                digest_events.emit("replay_item_failed", replay_id=job_id, company=company, error=str(exc)[:300],
                                   failed=replay_state["failed"], total=len(items))
        replay_state.update(status="complete", current=None)
        digest_events.emit("replay_finished", replay_id=job_id, found=len(items),
                           processed=replay_state["processed"], failed=replay_state["failed"])
    except Exception as exc:
        logging.getLogger("replay").exception("replay failed")
        replay_state.update(status="failed", current=None, error=str(exc)[:500])
        digest_events.emit("replay_failed", replay_id=job_id, error=str(exc)[:300])


# ---- WebSockets -------------------------------------------------------------------
@app.websocket("/stream/briefs")
async def stream_briefs(ws: WebSocket):
    await ws.accept()
    briefs_feed.clients.add(ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive; clients may ping
    except WebSocketDisconnect:
        briefs_feed.clients.discard(ws)


@app.websocket("/stream/activity")
async def stream_activity(ws: WebSocket):
    await ws.accept()
    for event in list(recent_events):  # replay recent history first
        await ws.send_text(json.dumps(event))
    activity_feed.clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        activity_feed.clients.discard(ws)

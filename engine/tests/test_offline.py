"""Offline tests (no network, no API key):  python -m pytest -q
The only fake is the LLM network call (see fake_llm); production code has no mock mode."""
import os
import sys

import pymupdf
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["DB_PATH"] = "/tmp/test_callwire.db"
os.environ["LLM_API_KEY"] = ""
os.environ["WATCH_MODE"] = "all"
if os.path.exists("/tmp/test_callwire.db"):
    os.remove("/tmp/test_callwire.db")

import flow  # noqa: E402
import settings  # noqa: E402
import store  # noqa: E402
from digest import events, llm_client, mapreduce  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from gateway.app import app, briefs_feed  # noqa: E402
from ingest.exchanges import looks_like_transcript  # noqa: E402
from ingest.scanner import in_scope  # noqa: E402
from reader.pdf_text import find_quarter  # noqa: E402

REAL_LLM = llm_client.call_llm


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    """Test double for the HTTP call to the LLM provider only."""
    def fake(system, user, retries=5, max_out=None):
        return {"tldr": ["t"], "management_commentary": ["m"], "guidance": [], "segment_performance": [],
                "key_metrics": [], "notable_qa": [], "risks": [], "tone": {"label": "neutral", "reason": "test"}}
    monkeypatch.setattr(llm_client, "call_llm", fake)
    events.shutdown.clear()  # an earlier test's app shutdown must not leak into this one


def make_pdf() -> bytes:
    doc = pymupdf.open()
    for n in range(6):
        page = doc.new_page()
        y = 60
        page.insert_text((50, 30), "ACME Ltd - Q1 FY26 Earnings Call Transcript", fontsize=9)
        body = "Moderator: Welcome to the Q1 FY26 earnings call of ACME Ltd.\nManagement: Revenue grew 12 percent to Rs 4,500 crore this quarter and margins were stable. " * 6
        for line in body.split("\n"):
            page.insert_text((50, y), line[:95], fontsize=10)
            y += 14
        page.insert_text((280, 820), f"Page {n + 1}", fontsize=8)
    return doc.tobytes()


ITEM = dict(company="ACME Ltd", symbol="ACME", scrip="500001", date="2025-07-24", url="https://x/y.pdf", source="BSE")


def test_transcript_filter():
    assert looks_like_transcript("Transcript of Earnings Call")
    assert not looks_like_transcript("Audio recording of earnings call")
    assert not looks_like_transcript("Board meeting")


def test_quarter_chunk_verify():
    assert find_quarter("the Q1 FY26 call") == "Q1 FY26"
    assert len(mapreduce.chunk(("x" * 500 + "\n\n") * 100)) > 3
    s = mapreduce.verify_metrics({"key_metrics": [{"value": "Rs 4,500 crore"}, {"value": "99%"}]}, "revenue 4,500 crore")
    assert [m["verified"] for m in s["key_metrics"]] == ["number_only", "no"]  # no quote given => never "full"


def test_pipeline_dedupe_api_ws():
    store.init()
    pdf = make_pdf()
    s = flow.process_filing(ITEM, pdf)
    assert s and s["quarter"] == "Q1 FY26" and "Page" not in store.get_brief(s["id"])["markdown"]
    assert flow.process_filing({**ITEM, "source": "NSE"}, pdf) is None  # cross-exchange duplicate

    app.state.no_watcher = True
    with TestClient(app) as c:
        assert c.get("/v1/briefs").json()[0]["company"] == "ACME Ltd"
        assert c.get(f"/v1/briefs/{s['id']}").json()["company"] == "ACME Ltd"
        assert "TL;DR" in c.get(f"/v1/briefs/{s['id']}/markdown").text
        assert c.get("/v1/briefs/99999").status_code == 404
        assert c.get("/").status_code == 200
        assert c.get("/activity").status_code == 200
        assert c.get("/v1/activity").status_code == 200
        with c.websocket_connect("/stream/briefs"):
            assert len(briefs_feed.clients) == 1


def test_chunk_oversized_paragraph():
    cs = mapreduce.chunk("word " * 5000, size=1000)
    assert len(cs) >= 10 and all(len(c) <= 1000 for c in cs)


def test_events_emitted():
    got = []
    events.listeners.append(got.append)
    try:
        events.set_context(company="X")
        events.emit("chunk_done", index=1, total=2, reply={"a": 1})
    finally:
        events.listeners.remove(got.append)
    assert got and got[0]["company"] == "X" and got[0]["reply"] == {"a": 1}


def test_no_mock_without_key(monkeypatch):
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        REAL_LLM("s", "u")


def test_watch_modes(monkeypatch):
    item = {"company": "Tata Motors Ltd", "symbol": "TATAMOTORS"}
    monkeypatch.setattr(settings, "WATCH_MODE", "all")
    assert in_scope({"company": "Anyone Ltd"})
    monkeypatch.setattr(settings, "WATCH_MODE", "watchlist")
    monkeypatch.setattr(settings, "WATCHLIST", ["tata motors"])
    monkeypatch.setattr(settings, "SYMBOLS", [])
    assert in_scope(item) and not in_scope({"company": "Anyone Ltd", "symbol": "ANY"})
    monkeypatch.setattr(settings, "WATCHLIST", [])
    monkeypatch.setattr(settings, "SYMBOLS", ["TATAMOTORS"])
    assert in_scope(item)


def test_daily_count():
    store.init()
    assert store.count_today() >= 0

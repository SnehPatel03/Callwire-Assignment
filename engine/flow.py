"""One filing through the whole pipeline: extract -> summarise -> store."""
import asyncio
import hashlib
import logging
import os
import pathlib

import settings
import store
from digest.events import emit, set_context
from digest.mapreduce import summarize
from digest.render import to_markdown
from ingest.scanner import dedupe_key
from reader.pdf_text import find_call_date, find_quarter, read_pdf

log = logging.getLogger("flow")


def process_filing(item: dict, pdf: bytes):
    """Blocking. Returns the saved summary, or None when it duplicates an earlier one."""
    set_context(company=item.get("company"), source=item.get("source"))
    emit("started", url=item.get("url"), pdf_bytes=len(pdf))

    text = read_pdf(pdf)
    emit("extracted", chars=len(text))
    if len(text) < 500:
        raise ValueError("no usable text (scanned PDF without OCR, or empty)")

    text_hash = hashlib.sha256(text.encode()).hexdigest()
    # The call date comes from the transcript itself; keep the filing date alongside.
    item = {**item, "filing_date": item["date"], "date": find_call_date(text) or item["date"]}
    key = dedupe_key(item)
    if store.is_known(key, text_hash):  # same call filed on NSE and BSE
        log.info("duplicate skipped: %s", key)
        emit("duplicate")
        return None

    item = {**item, "quarter": find_quarter(text)}
    summary = summarize(text, item)
    markdown = to_markdown(summary)
    summary["id"] = store.insert_brief(key, text_hash, summary, markdown)

    transcripts = pathlib.Path(os.path.dirname(settings.DB_PATH) or ".") / "transcripts"
    transcripts.mkdir(parents=True, exist_ok=True)
    (transcripts / f"{summary['id']}.txt").write_text(text, encoding="utf-8")  # cleaned transcript, for samples
    emit("saved", id=summary["id"])
    return summary


def make_handler(announce):
    """Build the async callback the scanner uses. `announce(summary)` pushes it to WebSocket clients."""
    async def handle(item, pdf):
        summary = await asyncio.to_thread(process_filing, item, pdf)
        if summary:
            await announce(summary)
    return handle

"""The polling loop: find new in-scope transcripts and hand each one to the pipeline."""
import asyncio
import logging
import re

import settings
import store
from . import exchanges

log = logging.getLogger("ingest")


def in_scope(item: dict) -> bool:
    """Is this company one we were asked to track?"""
    if settings.WATCH_MODE == "all":
        return True
    name = (item["company"] or "").lower()
    symbol = (item.get("symbol") or "").upper()
    return symbol in settings.SYMBOLS or any(w in name for w in settings.WATCHLIST)


def normalize_name(name: str) -> str:
    plain = (name or "").lower().replace("limited", "").replace("ltd", "")
    return re.sub(r"[^a-z0-9]", "", plain)


def dedupe_key(item: dict) -> str:
    """Same company + same day == same call, whichever exchange it came from."""
    return f"{normalize_name(item['company'])}|{item['date'][:10]}"


def scan_once(days: int | None = None) -> list[dict]:
    """One pass over the exchanges. Returns unseen, in-scope filings, newest first."""
    lookback = settings.LOOKBACK_DAYS if days is None else days
    fetchers = {"nse": exchanges.pull_nse, "bse": exchanges.pull_bse}
    items: list[dict] = []
    for name in settings.SOURCES:
        fetch = fetchers.get(name)
        if not fetch:
            continue
        try:
            items += fetch(lookback)
        except Exception as exc:  # one exchange down != pipeline down
            log.warning("%s failed: %s", fetch.__name__, exc)

    fresh = [
        i for i in items
        if in_scope(i) and not store.url_seen(i["url"]) and not store.is_known(dedupe_key(i))
    ]
    # Newest first, so a daily cap drops the oldest.
    return sorted(fresh, key=lambda i: i["date"], reverse=True)


async def run_forever(handle) -> None:
    """handle(item, pdf_bytes) is the pipeline callback."""
    while True:
        try:
            for item in await asyncio.to_thread(scan_once):
                cap = settings.MAX_SUMMARIES_PER_DAY
                if cap and store.count_today() >= cap:
                    log.warning("daily cap of %d summaries reached; remaining filings wait for tomorrow", cap)
                    break  # left unseen, so they are picked up again after the cap resets
                try:
                    pdf = await asyncio.to_thread(exchanges.fetch_pdf, item)
                    await handle(item, pdf)
                    store.mark_url_seen(item["url"])
                except Exception as exc:
                    log.error("item failed %s: %s", item["url"], exc)
        except Exception as exc:
            log.error("poll loop error: %s", exc)
        await asyncio.sleep(settings.POLL_SECONDS)

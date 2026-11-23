"""NSE + BSE announcement fetchers.

Both return normalised dicts: {company, symbol, scrip, date, url, source, text}.
"""
import logging
import re
from datetime import date, timedelta

import settings
from .session import PoliteSession

log = logging.getLogger("ingest")

NSE = PoliteSession(
    {"Referer": "https://www.nseindia.in/companies-listing/corporate-filings-announcements"},
    warm_url="https://www.nseindia.in",
    min_gap=1.5,
)
BSE = PoliteSession(
    {
        "Origin": "https://www.bseindia.com",
        "Referer": "https://www.bseindia.com/corporates/ann.html",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    },
    warm_url="https://www.bseindia.com/corporates/ann.html",
    min_gap=1.0,
)

_MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
_TRANSCRIPT = re.compile(r"transcript", re.I)


def to_iso(raw: str) -> str:
    """NSE '19-Nov-2026 20:23:07', BSE '2026-11-19T..' or '19-11-2026'  ->  '2026-11-19'."""
    raw = (raw or "").strip()
    if m := re.search(r"(\d{4})-(\d{2})-(\d{2})", raw):
        return m.group(0)
    if m := re.search(r"(\d{1,2})-([A-Za-z]{3})[a-z]*-(\d{4})", raw):
        return f"{m.group(3)}-{_MONTHS.get(m.group(2).lower(), 0):02d}-{int(m.group(1)):02d}"
    if m := re.search(r"(\d{2})-(\d{2})-(\d{4})", raw):
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return raw[:10]


def looks_like_transcript(text: str) -> bool:
    """Keep filings that say 'transcript'. Intimations and audio-only recordings never do,
    so they are skipped without a separate check."""
    return bool(_TRANSCRIPT.search(text or ""))


def pull_nse(days: int) -> list[dict]:
    start = (date.today() - timedelta(days=days)).strftime("%d-%m-%Y")
    end = date.today().strftime("%d-%m-%Y")
    # Per-symbol queries avoid the global feed's row cap.
    symbols = (settings.SYMBOLS if settings.WATCH_MODE == "watchlist" else []) or [None]

    rows: list = []
    for sym in symbols:
        params = {"index": "equities", "from_date": start, "to_date": end}
        if sym:
            params["symbol"] = sym
        data = NSE.get("https://www.nseindia.in/api/corporate-announcements", params=params).json()
        rows += data if isinstance(data, list) else []

    found = []
    for row in rows:
        blob = f"{row.get('desc', '')} {row.get('attchmntText', '')}"
        if looks_like_transcript(blob) and row.get("attchmntFile"):
            found.append(dict(
                company=row.get("sm_name") or row.get("symbol"),
                symbol=row.get("symbol"),
                scrip=None,
                date=to_iso(row.get("an_dt")),
                url=row["attchmntFile"],
                source="NSE",
                text=blob,
            ))
    return found


def pull_bse(days: int) -> list[dict]:
    start = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
    end = date.today().strftime("%Y%m%d")
    endpoint = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"

    found = []
    for page in (1, 2, 3):
        resp = BSE.get(endpoint, params={
            "pageno": page, "strCat": "Company Update", "subcategory": "Earnings Call Transcript",
            "strPrevDate": start, "strToDate": end, "strScrip": "", "strSearch": "P", "strType": "C",
        })
        if resp.status_code == 403:
            raise RuntimeError("BSE API 403: blocked by BSE Akamai/WAF (NSE remains available)")
        resp.raise_for_status()
        rows = resp.json().get("Table") or []
        for row in rows:
            blob = f"{row.get('NEWSSUB', '')} {row.get('HEADLINE', '')}"
            if row.get("ATTACHMENTNAME") and looks_like_transcript(blob):
                found.append(dict(
                    company=row.get("SLONGNAME"),
                    symbol=None,
                    scrip=str(row.get("SCRIP_CD")),
                    date=to_iso(row.get("NEWS_DT")),
                    url="https://www.bseindia.com/xml-data/corpfiling/AttachLive/" + row["ATTACHMENTNAME"],
                    source="BSE",
                    text=blob,
                ))
        if len(rows) < 50:  # last page
            break
    return found


def fetch_pdf(item: dict) -> bytes:
    session = NSE if item["source"] == "NSE" else BSE
    resp = session.get(item["url"], headers={"Accept": "application/pdf,*/*"})
    if not resp.content.startswith(b"%PDF"):
        raise ValueError("not a PDF (blocked or HTML error page)")
    return resp.content

"""SQLite persistence: finished briefs plus the set of filing URLs already handled."""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager

import settings

_guard = threading.Lock()  # one writer/reader at a time; plenty for this workload


@contextmanager
def _conn():
    with _guard:
        con = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
        con.row_factory = sqlite3.Row
        try:
            with con:  # commit on success, roll back on error
                yield con
        finally:
            con.close()


def init() -> None:
    os.makedirs(os.path.dirname(settings.DB_PATH) or ".", exist_ok=True)
    with _conn() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS briefs(
                   id INTEGER PRIMARY KEY,
                   dedupe_key TEXT UNIQUE,
                   text_hash TEXT UNIQUE,
                   company TEXT, quarter TEXT, call_date TEXT, source TEXT, url TEXT,
                   payload TEXT, markdown TEXT,
                   created TEXT DEFAULT CURRENT_TIMESTAMP)"""
        )
        con.execute("CREATE TABLE IF NOT EXISTS seen_urls(url TEXT PRIMARY KEY)")


# ---- filing URLs we've already dealt with -----------------------------------------
def url_seen(url: str) -> bool:
    with _conn() as con:
        return con.execute("SELECT 1 FROM seen_urls WHERE url=?", (url,)).fetchone() is not None


def mark_url_seen(url: str) -> None:
    with _conn() as con:
        con.execute("INSERT OR IGNORE INTO seen_urls VALUES(?)", (url,))


# ---- briefs -----------------------------------------------------------------------
def is_known(dedupe_key=None, text_hash=None) -> bool:
    """True if a brief with this company|date key OR this transcript hash exists."""
    with _conn() as con:
        row = con.execute(
            "SELECT 1 FROM briefs WHERE dedupe_key=? OR text_hash=?", (dedupe_key, text_hash)
        ).fetchone()
        return row is not None


def insert_brief(dedupe_key: str, text_hash: str, summary: dict, markdown: str) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO briefs(dedupe_key,text_hash,company,quarter,call_date,source,url,payload,markdown)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (
                dedupe_key, text_hash,
                summary.get("company"), summary.get("quarter"), summary.get("call_date"),
                summary.get("source"), summary.get("source_url"),
                json.dumps(summary), markdown,
            ),
        )
        return cur.lastrowid


def count_today() -> int:
    """Briefs created today (UTC) - feeds the daily LLM-cost cap."""
    with _conn() as con:
        return con.execute("SELECT COUNT(*) FROM briefs WHERE date(created)=date('now')").fetchone()[0]


def list_briefs() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id,company,quarter,call_date,source,created FROM briefs ORDER BY id DESC"
        )
        return [dict(r) for r in rows]


def get_brief(brief_id: int):
    with _conn() as con:
        row = con.execute("SELECT * FROM briefs WHERE id=?", (brief_id,)).fetchone()
        return dict(row) if row else None

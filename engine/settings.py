"""Runtime settings, read once from the environment (and a local .env file).

Other modules do `import settings` and read attributes at call time, so tests can
monkeypatch values without reloading anything.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _list(name: str, fold=str.lower) -> list[str]:
    """Comma-separated env var -> list of cleaned, case-folded items."""
    return [fold(x.strip()) for x in os.getenv(name, "").split(",") if x.strip()]


# --- LLM provider (any OpenAI-compatible endpoint) -------------------------------
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
LLM_TPM = int(os.getenv("LLM_TPM", "7000"))        # tokens/min budget (Groq free tier ~8000)
LLM_MAX_OUT = int(os.getenv("LLM_MAX_OUT", "1200"))
CHUNK_CHARS = int(os.getenv("CHUNK_CHARS", "4000"))

# --- Polling ---------------------------------------------------------------------
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "120"))
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "3"))
SOURCES = [x.strip().lower() for x in os.getenv("SOURCES", "nse,bse").split(",")]
DB_PATH = os.getenv("DB_PATH", "data/callwire.db")

# --- Which companies -------------------------------------------------------------
WATCHLIST = _list("WATCHLIST")                       # name fragments, lower-cased
SYMBOLS = _list("SYMBOLS", fold=str.upper)           # optional NSE symbols, upper-cased

# "watchlist": only WATCHLIST / SYMBOLS (cheap, matches the 5-10 company scope)
# "all":       every concall transcript on NSE/BSE (scanning is free, each summary costs tokens)
# Unset => "watchlist" if a WATCHLIST/SYMBOLS is given, otherwise "all".
WATCH_MODE = os.getenv("WATCH_MODE", "").strip().lower() or ("watchlist" if (WATCHLIST or SYMBOLS) else "all")
if WATCH_MODE not in ("watchlist", "all"):
    raise ValueError("WATCH_MODE must be 'watchlist' or 'all'")
if WATCH_MODE == "watchlist" and not (WATCHLIST or SYMBOLS):
    raise ValueError("WATCH_MODE=watchlist needs WATCHLIST or SYMBOLS (or set WATCH_MODE=all)")

# Safety valve on LLM spend: max new summaries per UTC day. 0 = unlimited.
# Defaults to 40 in "all" mode so an unattended run cannot burn the whole API budget.
# An empty value in .env falls back to the default.
MAX_SUMMARIES_PER_DAY = int(os.getenv("MAX_SUMMARIES_PER_DAY") or ("40" if WATCH_MODE == "all" else "0"))

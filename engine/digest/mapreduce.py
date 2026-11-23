"""Map-reduce summariser.

MAP:    per-chunk fact extraction, with verbatim quotes for every number.
REDUCE: merge the partial results into the fixed schema.
Anti-hallucination: grounded prompts + a post-hoc check that every number in key_metrics
really appears in the transcript.
"""
import difflib
import hashlib
import json
import os
import pathlib
import re
import textwrap

import settings
from . import llm_client
from .events import emit

SCHEMA = {
    "tldr": [],
    "management_commentary": [],
    "guidance": [],
    "segment_performance": [{"segment": "", "notes": ""}],
    "key_metrics": [{"metric": "", "entity": "", "period": "", "value": "", "context": "", "quote": ""}],
    "notable_qa": [{"question": "", "answer": "", "asked_by": "", "answered_by": ""}],
    "risks": [],
    "tone": {"label": "", "reason": ""},
}
RULES = "Use ONLY the provided text. Never invent or infer numbers, names or facts. If something is not stated, omit it. Output JSON only."


# ---- chunking ---------------------------------------------------------------------
def chunk(text: str, size: int | None = None) -> list[str]:
    """Split on paragraph breaks into pieces of at most `size` characters."""
    size = size or settings.CHUNK_CHARS
    if not text or not text.strip():
        return []
    chunks, current = [], ""
    for para in text.split("\n\n"):
        if len(para) + 2 <= size:
            pieces = [para]
        else:  # a single paragraph bigger than a chunk
            pieces = textwrap.wrap(para, size - 2, break_long_words=True, replace_whitespace=False)
        for piece in pieces:
            if current and len(current) + len(piece) + 2 > size:
                chunks.append(current.rstrip())
                current = ""
            current += piece + "\n\n"
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


# ---- map --------------------------------------------------------------------------
def _extract_facts(text: str, i: int, n: int) -> dict:
    return llm_client.call_llm(
        f"You extract facts from part {i+1}/{n} of an Indian earnings-call transcript. {RULES}",
        f"Return JSON with keys {json.dumps(SCHEMA)}. For key_metrics give: entity (Consolidated / JLR / India PV / a segment...), period (e.g. Q2 FY27, H1 FY27, FY28 target) and a verbatim 'quote' (max 25 words) that CONTAINS the number. Never label a segment's number as consolidated. For guidance, start each item with entity and period. For notable_qa use the analyst or questioner's name and firm for asked_by. Use the named management executive or speaker who gives the answer for answered_by; if no person is named, use 'Management'. Keep asked_by and answered_by names. Empty lists if nothing relevant.\n\nTEXT:\n{text}",
    )


def map_chunk(text: str, i: int, n: int) -> dict:
    """Disk-cached so a failed run resumes instead of redoing every chunk."""
    cache_dir = pathlib.Path(os.path.dirname(settings.DB_PATH) or ".") / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / (hashlib.sha1((settings.LLM_MODEL + text).encode()).hexdigest() + ".json")

    cached = cache_file.exists()
    if cached:
        result = json.loads(cache_file.read_text(encoding="utf-8"))
    else:
        result = _extract_facts(text, i, n)
        cache_file.write_text(json.dumps(result), encoding="utf-8")
    emit("chunk_done", index=i + 1, total=n, cached=cached, reply=result)
    return result


# ---- reduce -----------------------------------------------------------------------
def _merge(parts: list[dict], final: bool = False) -> dict:
    limits = (
        "max 8 items per list, max 6 Q&As, max 10 key_metrics"
        if final else
        "max 3 items per list, max 4 key_metrics, max 2 Q&As, each item under 30 words; keep entity, period and verbatim quote for every key_metric; keep asked_by and answered_by names"
    )
    merged = llm_client.call_llm(
        f"You merge partial extractions of ONE earnings call into a summary. {RULES} Deduplicate; keep the sharpest items; tldr = 3-5 short lines; {limits}; each item under 40 words; keep entity, period and verbatim quote for every key_metric; keep asked_by and answered_by names.",
        f"Return JSON with exactly these keys: {json.dumps(SCHEMA)}. tone.label is one of positive/neutral/cautious/negative with a reason grounded in the text.\n\nPARTS:\n{json.dumps(parts)}",
        max_out=3500 if final else None,
    )
    emit("merge_done", final=final, reply=merged)
    return merged


def reduce_parts(parts: list[dict], group_chars: int = 15500, final_chars: int = 10500) -> dict:
    """Hierarchical reduce sized to the TPM budget: few, fat merge calls instead of many small ones."""
    while len(parts) > 1 and len(json.dumps(parts)) > final_chars:
        groups, current = [], []
        for part in parts:
            if current and len(json.dumps(current + [part])) > group_chars:
                groups.append(current)
                current = []
            current.append(part)
        groups.append(current)
        if len(groups) == len(parts):  # nothing grouped: force progress by pairing
            groups = [parts[i:i + 2] for i in range(0, len(parts), 2)]
        emit("merge_start", parts_in=len(parts), calls=sum(1 for g in groups if len(g) > 1), final=False)
        parts = [_merge(g) if len(g) > 1 else g[0] for g in groups]
    emit("merge_start", parts_in=len(parts), calls=1, final=True)
    return _merge(parts, final=True)


# ---- verification -----------------------------------------------------------------
def _squash(t: str) -> str:
    return re.sub(r"\s+", " ", t.lower().replace("’", "'").replace("‑", "-")).strip()


def verify_metrics(summary: dict, transcript: str) -> dict:
    """Mark every key metric:
    full         quote found in the transcript AND the metric's number is inside the quote
    number_only  the number exists somewhere in the transcript, but the quote doesn't match
    no           neither
    """
    norm = _squash(transcript)
    flat = norm.replace(",", "")
    for metric in summary.get("key_metrics", []):
        quote = _squash(str(metric.get("quote", "")))
        numbers = re.findall(r"\d+(?:\.\d+)?", str(metric.get("value", "")).replace(",", ""))
        number_in_quote = bool(numbers) and all(n in quote.replace(",", "") for n in numbers)
        quote_found = bool(quote) and (
            quote in norm
            or difflib.SequenceMatcher(None, norm, quote, autojunk=False)
                      .find_longest_match(0, len(norm), 0, len(quote)).size >= 0.85 * len(quote)
        )
        if number_in_quote and quote_found:
            metric["verified"] = "full"
        elif numbers and all(n in flat for n in numbers):
            metric["verified"] = "number_only"
        else:
            metric["verified"] = "no"
    return summary


# ---- entry point ------------------------------------------------------------------
def summarize(text: str, meta: dict) -> dict:
    chunks = chunk(text)
    if not chunks:
        raise ValueError("empty transcript")
    emit("chunks_ready", total=len(chunks))

    parts = [map_chunk(c, i, len(chunks)) for i, c in enumerate(chunks)]
    final = reduce_parts(parts)
    final = {key: final.get(key, default) for key, default in SCHEMA.items()}  # fixed schema, nothing extra
    final = verify_metrics(final, text)

    return {
        "company": meta["company"],
        "scrip_code": meta.get("scrip"),
        "nse_symbol": meta.get("symbol"),
        "quarter": meta.get("quarter"),
        "call_date": meta["date"],
        "filing_date": meta.get("filing_date"),
        "source": meta["source"],
        "source_url": meta["url"],
        "chunks_processed": len(chunks),
        **final,
    }

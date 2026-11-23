"""Thin client for any OpenAI-compatible chat-completions endpoint.

Handles free-tier token-per-minute budgeting, retries, and JSON recovery
(code fences, truncated output).
"""
import json
import logging
import re
import time

import httpx

import settings
from .events import Stopped, emit, pause, shutdown

log = logging.getLogger("digest")

_recent: list[tuple[float, int]] = []  # (timestamp, tokens) of requests in the last minute


def _wait_for_budget(estimate: int) -> None:
    while True:
        now = time.time()
        _recent[:] = [(t, n) for t, n in _recent if now - t < 60]
        used = sum(n for _, n in _recent)
        if used + estimate <= settings.LLM_TPM or not _recent:
            return
        wait = max(1, 60 - (now - _recent[0][0]) + 1)
        emit("rate_wait", seconds=round(wait),
             reason=f"{used}+{estimate} tokens would exceed LLM_TPM={settings.LLM_TPM}")
        pause(wait)


def call_llm(system: str, user: str, retries: int = 5, max_out: int | None = None) -> dict:
    """Send one chat request and return the parsed JSON object from the reply."""
    if shutdown.is_set():
        raise Stopped()
    if not settings.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY is not set - refusing to produce a summary without a real LLM")

    max_out = max_out or settings.LLM_MAX_OUT
    body = {
        "model": settings.LLM_MODEL,
        "temperature": 0.1,
        "max_tokens": max_out,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if "gpt-oss" in settings.LLM_MODEL:
        body["reasoning_effort"] = "low"

    estimate = int((len(system) + len(user)) / 3.2) + max_out
    if estimate > settings.LLM_TPM:
        raise RuntimeError(f"request ~{estimate} tokens exceeds LLM_TPM={settings.LLM_TPM}; lower CHUNK_CHARS/LLM_MAX_OUT")

    for attempt in range(retries):
        try:
            _wait_for_budget(estimate)
            _recent.append((time.time(), estimate))
            resp = httpx.post(
                settings.LLM_BASE_URL.rstrip("/") + "/chat/completions",
                timeout=180,
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
                json=body,
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                pause(float(resp.headers.get("retry-after", 2 ** (attempt + 3))))
                continue
            if 400 <= resp.status_code < 500:
                raise RuntimeError(f"LLM HTTP {resp.status_code} model={settings.LLM_MODEL}: {resp.text[:300]}")

            data = resp.json()
            real_tokens = (data.get("usage") or {}).get("total_tokens")
            if real_tokens:  # swap our estimate for the provider's real count
                _recent[-1] = (_recent[-1][0], real_tokens)
            choice = data["choices"][0]
            try:
                return parse_json(choice["message"]["content"] or "")
            except ValueError:
                if choice.get("finish_reason") == "length":  # truncated: ask for less next time
                    body["messages"][1]["content"] = (
                        user + "\n\nIMPORTANT: your last answer was cut off. Be much shorter: at most 3 items per list."
                    )
                    log.warning("output truncated at max_tokens=%d", max_out)
                raise
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            log.warning("llm attempt %d failed: %s", attempt + 1, exc)
            emit("llm_retry", attempt=attempt + 1, error=str(exc)[:200])
            pause(2 if "truncated" not in str(exc) else 0)
    raise RuntimeError("LLM failed after retries")


def repair_json(s: str):
    """Close a truncated JSON document at its last complete element."""
    stack, in_string, escaped, candidates = [], False, False, []
    for i, ch in enumerate(s):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack:
                stack.pop()
            candidates.append(s[: i + 1] + "".join(reversed(stack)))
        elif ch == ",":
            candidates.append(s[:i] + "".join(reversed(stack)))
    for candidate in reversed(candidates[-40:]):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError("unrepairable JSON")


def parse_json(s: str):
    s = re.sub(r"^```(?:json)?|```$", "", s.strip(), flags=re.M).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", s, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        try:
            return repair_json(s[s.find("{"):])
        except ValueError:
            raise ValueError("no valid JSON in LLM output")

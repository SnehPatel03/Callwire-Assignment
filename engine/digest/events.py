"""Shutdown flag + live progress events shared by the whole summarisation stage."""
import contextvars
import logging
import threading
import time

log = logging.getLogger("digest")

shutdown = threading.Event()   # set by the server on exit so worker threads stop waiting


class Stopped(Exception):
    """Raised inside a worker thread when the service is shutting down."""


def pause(seconds: float) -> None:
    """Interruptible sleep."""
    if shutdown.wait(seconds):
        raise Stopped()


listeners: list = []           # callables taking one event dict (the gateway registers one)
_context = contextvars.ContextVar("digest_ctx", default={})


def set_context(**fields) -> None:
    """Fields (company, source...) attached to every event emitted from this thread."""
    _context.set(fields)


def emit(kind: str, **fields) -> None:
    event = {"ts": time.time(), "kind": kind, **_context.get(), **fields}
    for listener in listeners:
        try:
            listener(event)
        except Exception:
            log.exception("listener failed")

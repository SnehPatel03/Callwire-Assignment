import { useCallback, useEffect, useRef, useState } from "react";
import { briefsSocketUrl, getBrief, listBriefs, toRow } from "../lib/api";
import { timeOf } from "../lib/format";
import type { Brief, BriefRow, Link } from "../lib/types";

const newestFirst = (rows: BriefRow[]) =>
  [...rows].sort((a, b) => timeOf(b.callDate) - timeOf(a.callDate) || b.id - a.id);

const msg = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong");

/** The list of briefs, kept current through the /stream/briefs WebSocket. */
export function useWire() {
  const [rows, setRows] = useState<BriefRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [link, setLink] = useState<Link>("connecting");
  const [fresh, setFresh] = useState<Set<number>>(new Set());

  const reload = useCallback(async () => {
    try {
      setRows(newestFirst(await listBriefs()));
      setError(null);
    } catch (e) {
      setError(msg(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let timer: number | undefined;
    let attempt = 0;
    let closed = false;

    const onMessage = (raw: unknown) => {
      let data: unknown;
      try {
        data = typeof raw === "string" ? JSON.parse(raw) : null;
      } catch {
        return;
      }
      if (!data || typeof data !== "object" || !("id" in data) || !("company" in data)) return;
      const row = toRow(data as Record<string, unknown>);
      setRows((prev) => newestFirst([row, ...prev.filter((r) => r.id !== row.id)]));
      setFresh((prev) => new Set(prev).add(row.id));
    };

    const open = () => {
      setLink("connecting");
      socket = new WebSocket(briefsSocketUrl());
      socket.onopen = () => {
        if (attempt > 0) void reload(); // catch up on anything missed while offline
        attempt = 0;
        setLink("live");
      };
      socket.onmessage = (ev) => onMessage(ev.data);
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (closed) return;
        setLink("offline");
        timer = window.setTimeout(open, Math.min(15_000, 1_000 * 2 ** attempt++));
      };
    };

    open();
    return () => {
      closed = true;
      window.clearTimeout(timer);
      socket?.close();
    };
  }, [reload]);

  const dismiss = useCallback((id: number) => {
    setFresh((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }, []);

  return { rows, loading, error, link, fresh, reload, dismiss };
}

/** One full brief, cached per id. */
export function useBrief(id: number) {
  const cache = useRef(new Map<number, Brief>());
  const [brief, setBrief] = useState<Brief | null>(cache.current.get(id) ?? null);
  const [loading, setLoading] = useState(!cache.current.has(id));
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const hit = cache.current.get(id);
    if (hit) {
      setBrief(hit);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getBrief(id)
      .then((b) => {
        if (cancelled) return;
        cache.current.set(id, b);
        setBrief(b);
      })
      .catch((e) => !cancelled && setError(msg(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [id, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { brief, loading, error, retry };
}

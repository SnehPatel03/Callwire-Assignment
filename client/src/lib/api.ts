import type { ActivityEvent, Brief, BriefRow } from "./types";

const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

async function call(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText || "Request failed"}`);
  return res;
}

export function toRow(raw: Record<string, unknown>): BriefRow {
  return {
    id: Number(raw.id),
    company: String(raw.company ?? "Unknown company"),
    quarter: String(raw.quarter ?? ""),
    callDate: (raw.call_date ?? null) as string | null,
    source: (raw.source ?? null) as string | null,
  };
}

/** GET /v1/briefs */
export async function listBriefs(): Promise<BriefRow[]> {
  const data = await (await call("/v1/briefs")).json();
  return Array.isArray(data) ? data.map((r) => toRow(r as Record<string, unknown>)) : [];
}

/** GET /v1/briefs/{id} */
export async function getBrief(id: number): Promise<Brief> {
  return (await (await call(`/v1/briefs/${id}`)).json()) as Brief;
}

/** GET /v1/briefs/{id}/markdown */
export async function getMarkdown(id: number): Promise<string> {
  return (await call(`/v1/briefs/${id}/markdown`)).text();
}

export interface ReplayJob {
  id: string;
  status: "idle" | "scanning" | "running" | "complete" | "failed";
  days: number;
  found: number;
  processed: number;
  failed: number;
  current: string | null;
  error: string | null;
}

/** Start a replay and poll its status separately while it runs. */
export async function startReplay(days: number): Promise<ReplayJob> {
  return (await call(`/v1/replay?days=${days}`, { method: "POST" })).json();
}

export async function getReplay(id: string): Promise<ReplayJob> {
  return (await call(`/v1/replay/${encodeURIComponent(id)}`)).json();
}

/** GET /v1/activity */
export async function getActivity(): Promise<ActivityEvent[]> {
  const data = await (await call("/v1/activity")).json();
  return Array.isArray(data) ? data : [];
}

/** WebSocket the UI itself listens on (goes through the dev proxy when there is one). */
export function briefsSocketUrl(): string {
  if (BASE) return BASE.replace(/^http/, "ws") + "/stream/briefs";
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/stream/briefs`;
}

/** Addresses to hand to OTHER apps: always the engine itself, never the dev proxy. */
export function externalSocketUrls(): { briefs: string; activity: string } {
  const target = (import.meta.env.VITE_API_BASE || import.meta.env.VITE_API_TARGET || "http://localhost:8000") as string;
  const base = target.replace(/\/$/, "").replace(/^http/, "ws");
  return { briefs: `${base}/stream/briefs`, activity: `${base}/stream/activity` };
}

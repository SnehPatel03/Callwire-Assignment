/** One row of GET /v1/briefs */
export interface BriefRow {
  id: number;
  company: string;
  quarter: string;
  callDate: string | null;
  source: string | null;
}

/**
 * One full brief from GET /v1/briefs/{id}.
 * The list-like fields come from an LLM, so they stay `unknown` here and are
 * coerced into safe shapes by lib/shape.ts before rendering.
 */
export interface Brief {
  id: number;
  company: string;
  quarter: string;
  scrip_code?: string | number | null;
  nse_symbol?: string | null;
  call_date?: string | null;
  filing_date?: string | null;
  source?: string | null;
  source_url?: string | null;
  tldr?: unknown;
  management_commentary?: unknown;
  guidance?: unknown;
  segment_performance?: unknown;
  key_metrics?: unknown;
  notable_qa?: unknown;
  risks?: unknown;
  tone?: unknown;
}

/** One pipeline event from GET /v1/activity or /stream/activity */
export type ActivityEvent = Record<string, unknown> & { seq?: number; ts?: number; kind?: string };

export type Link = "connecting" | "live" | "offline";

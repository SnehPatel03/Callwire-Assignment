/**
 * The summary comes from an LLM, so a list may arrive as a string, an array of
 * strings, or an array of objects. These helpers turn whatever came back into a
 * predictable shape so the views never crash on odd input.
 */
export type Rec = Record<string, unknown>;

export const isRec = (v: unknown): v is Rec => typeof v === "object" && v !== null && !Array.isArray(v);
const isPlain = (v: unknown): v is string | number | boolean =>
  typeof v === "string" || typeof v === "number" || typeof v === "boolean";

/** Anything -> a flat list of non-empty strings (bullets stripped, newlines split). */
export function toLines(v: unknown): string[] {
  if (v === null || v === undefined) return [];
  if (typeof v === "string") {
    return v.split(/\n+/).map((s) => s.replace(/^[-•*–]\s+/, "").trim()).filter(Boolean);
  }
  if (isPlain(v)) return [String(v)];
  if (Array.isArray(v)) return v.flatMap(toLines);
  if (isRec(v)) {
    const joined = Object.values(v).filter(isPlain).map(String).join(" — ").trim();
    return joined ? [joined] : [];
  }
  return [];
}

/** Anything -> a list of objects (non-objects are dropped). */
export function toRecords(v: unknown): Rec[] {
  if (Array.isArray(v)) return v.filter(isRec);
  return isRec(v) ? [v] : [];
}

/** Read a string field, trying several key names. */
export function field(r: Rec, ...keys: string[]): string {
  for (const k of keys) {
    const v = r[k];
    if (isPlain(v) && String(v).trim() !== "") return String(v);
  }
  return "";
}

export interface ToneInfo {
  label: string;
  reason: string;
}

export function readTone(v: unknown): ToneInfo | null {
  if (typeof v === "string" && v.trim()) return { label: v.trim(), reason: "" };
  if (isRec(v)) {
    const label = field(v, "label", "tone", "sentiment");
    const reason = field(v, "reason", "why", "rationale");
    if (label || reason) return { label: label || "—", reason };
  }
  return null;
}

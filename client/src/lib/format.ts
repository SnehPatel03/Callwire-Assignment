const fmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });

/** 'YYYY-MM-DD' is read as a local date so the day never shifts with the time zone. */
function toDate(v?: string | null): Date | null {
  if (!v) return null;
  const d = /^\d{4}-\d{2}-\d{2}$/.test(v) ? new Date(`${v}T00:00:00`) : new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function timeOf(v?: string | null): number {
  return toDate(v)?.getTime() ?? 0;
}

export function prettyDate(v?: string | null): string {
  const d = toDate(v);
  return d ? fmt.format(d) : "—";
}

/** 'Today' / 'Yesterday' / '12 Nov 2026' */
export function dayLabel(v?: string | null): string {
  const d = toDate(v);
  if (!d) return "Undated";
  const midnight = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((midnight(new Date()) - midnight(d)) / 86_400_000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return fmt.format(d);
}

export type ToneKind = "good" | "warn" | "bad" | "flat";

export function toneKind(label: string): ToneKind {
  const t = label.toLowerCase();
  if (/(negat|bearish|weak|worr|pessimis)/.test(t)) return "bad";
  if (/(posit|optimis|bullish|confiden|upbeat|strong|constructive)/.test(t)) return "good";
  if (/(cautio|mixed|measured|guarded|prudent|balanced)/.test(t)) return "warn";
  return "flat";
}

export function clock(ts: unknown): string {
  const n = Number(ts);
  if (!n) return "";
  return new Date(n * 1000).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

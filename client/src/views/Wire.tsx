import { useMemo, useState } from "react";
import { dayLabel } from "../lib/format";
import type { BriefRow } from "../lib/types";

interface Props {
  rows: BriefRow[];
  loading: boolean;
  error: string | null;
  fresh: Set<number>;
  onOpen: (id: number) => void;
  onRetry: () => void;
}

export function Wire({ rows, loading, error, fresh, onOpen, onRetry }: Props) {
  const [query, setQuery] = useState("");
  const [quarter, setQuarter] = useState("all");

  const quarters = useMemo(() => [...new Set(rows.map((r) => r.quarter).filter(Boolean))], [rows]);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((r) => (quarter === "all" || r.quarter === quarter) && (!q || r.company.toLowerCase().includes(q)));
  }, [rows, query, quarter]);

  return (
    <div className="page">
      <div className="page-head">
        <h1>The wire</h1>
        <p className="quiet">Every earnings call the watcher has picked up, newest first. New ones land here on their own.</p>
      </div>

      <div className="toolbar">
        <input
          className="field"
          type="search"
          placeholder="Filter by company"
          aria-label="Filter by company"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {quarters.length > 1 && (
          <div className="chips" role="group" aria-label="Quarter">
            {["all", ...quarters].map((q) => (
              <button key={q} className={`chip${quarter === q ? " on" : ""}`} onClick={() => setQuarter(q)}>
                {q === "all" ? "All quarters" : q}
              </button>
            ))}
          </div>
        )}
        <span className="count mono" aria-live="polite">
          {loading ? "loading…" : `${shown.length} ${shown.length === 1 ? "call" : "calls"}`}
        </span>
      </div>

      {error && (
        <div className="notice bad" role="alert">
          <span>Couldn’t load the briefs ({error}). Is the engine running?</span>
          <button className="btn" onClick={onRetry}>Try again</button>
        </div>
      )}

      {loading && !error && (
        <div className="cards" aria-hidden="true">
          {Array.from({ length: 6 }).map((_, i) => (
            <div className="card ghost" key={i} />
          ))}
        </div>
      )}

      {!loading && !error && shown.length === 0 && (
        <div className="notice">
          {rows.length === 0
            ? "Nothing here yet. The watcher is polling; use Replay to pull recent transcripts straight away."
            : "No company matches that filter."}
        </div>
      )}

      <div className="cards">
        {shown.map((r) => (
          <a
            key={r.id}
            href={`#/call/${r.id}`}
            className={`card${fresh.has(r.id) ? " fresh" : ""}`}
            onClick={() => onOpen(r.id)}
          >
            <span className="card-top">
              <span className="mono q">{r.quarter || "—"}</span>
              {fresh.has(r.id) && <span className="flag">new</span>}
            </span>
            <span className="card-name">{r.company}</span>
            <span className="card-foot mono">
              {dayLabel(r.callDate)}
              {r.source && <span> · {r.source}</span>}
            </span>
          </a>
        ))}
      </div>
    </div>
  );
}

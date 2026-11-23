import type { ReactNode } from "react";
import { field, toLines, toRecords, type ToneInfo } from "../lib/shape";
import { toneKind } from "../lib/format";

export function Bullets({ items }: { items: unknown }) {
  const lines = toLines(items);
  if (!lines.length) return null;
  return (
    <ul className="bullets">
      {lines.map((l, i) => (
        <li key={i}>{l}</li>
      ))}
    </ul>
  );
}

export function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="block">
      <h3 className="block-title">{title}</h3>
      {children}
    </section>
  );
}

export function Segments({ items }: { items: unknown }) {
  const rows = toRecords(items);
  if (!rows.length) return null;
  return (
    <dl className="segments">
      {rows.map((r, i) => (
        <div key={i}>
          <dt>{field(r, "segment", "name", "title") || `Segment ${i + 1}`}</dt>
          <dd>{field(r, "notes", "note", "performance", "description")}</dd>
        </div>
      ))}
    </dl>
  );
}

const CHECK: Record<string, { text: string; cls: string; hint: string }> = {
  full: { text: "verified", cls: "ok", hint: "Quote and number both found in the transcript" },
  number_only: { text: "number only", cls: "mid", hint: "Number is in the transcript, but the quote didn't match. Check by hand" },
  no: { text: "unverified", cls: "low", hint: "Number not found in the transcript. Check by hand" },
};

export function MetricsTable({ items }: { items: unknown }) {
  const rows = toRecords(items);
  if (!rows.length) return <p className="quiet">No numbers were extracted for this call.</p>;
  return (
    <div className="table-wrap">
      <table className="grid-table">
        <thead>
          <tr>
            <th>Metric</th>
            <th>Scope</th>
            <th>Value</th>
            <th>Context</th>
            <th>Check</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const check = CHECK[field(r, "verified")] ?? CHECK.no;
            const scope = [field(r, "entity"), field(r, "period")].filter(Boolean).join(" · ");
            const quote = field(r, "quote");
            return (
              <tr key={i}>
                <td className="strong">{field(r, "metric", "name", "title")}</td>
                <td className="quiet">{scope || "—"}</td>
                <td className="mono value">{field(r, "value", "amount")}</td>
                <td>
                  {field(r, "context")}
                  {quote && <span className="quote">“{quote}”</span>}
                </td>
                <td>
                  <span className={`check ${check.cls}`} title={check.hint}>
                    {check.text}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function QAList({ items }: { items: unknown }) {
  const rows = toRecords(items).filter((r) => field(r, "question", "q"));
  if (!rows.length) return <p className="quiet">No Q&amp;A was captured for this call.</p>;
  return (
    <ol className="qa">
      {rows.map((r, i) => (
        <li key={i}>
          <div className="qa-line">
            <span className="qa-tag">Q</span>
            <div>
              <p className="qa-text">{field(r, "question", "q")}</p>
              <p className="qa-who">{field(r, "asked_by", "analyst") || "Analyst not stated"}</p>
            </div>
          </div>
          <div className="qa-line">
            <span className="qa-tag alt">A</span>
            <div>
              <p className="qa-text">{field(r, "answer", "a", "response") || "No answer recorded."}</p>
              <p className="qa-who">{field(r, "answered_by") || "Management"}</p>
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

export function TonePill({ tone }: { tone: ToneInfo | null }) {
  if (!tone) return null;
  return (
    <span className={`tone tone-${toneKind(tone.label)}`} title={tone.reason || tone.label}>
      <i aria-hidden="true" />
      {tone.label}
    </span>
  );
}

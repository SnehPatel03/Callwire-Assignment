import { useState } from "react";
import { getMarkdown } from "../lib/api";
import { prettyDate } from "../lib/format";
import { toLines, toRecords, readTone } from "../lib/shape";
import { useBrief } from "../hooks/useWire";
import { Block, Bullets, MetricsTable, QAList, Segments, TonePill } from "../ui/Blocks";
import { useCopy } from "../ui/useCopy";

type Tab = "overview" | "numbers" | "qa" | "risks";

export function Reader({ id }: { id: number }) {
  const { brief, loading, error, retry } = useBrief(id);
  const [tab, setTab] = useState<Tab>("overview");
  const { copied, copy } = useCopy();
  const [failed, setFailed] = useState(false);

  const back = <a className="back mono" href="#/">← The wire</a>;

  if (loading) {
    return (
      <div className="page narrow" aria-busy="true">
        {back}
        <div className="bar tall" />
        <div className="bar" />
        <div className="bar" />
      </div>
    );
  }
  if (error || !brief) {
    return (
      <div className="page narrow">
        {back}
        <div className="notice bad" role="alert">
          <span>Couldn’t load this brief ({error ?? "not found"}).</span>
          <button className="btn" onClick={retry}>Try again</button>
        </div>
      </div>
    );
  }

  const tone = readTone(brief.tone);
  const counts: Record<Tab, number> = {
    overview: toLines(brief.management_commentary).length + toLines(brief.guidance).length + toRecords(brief.segment_performance).length,
    numbers: toRecords(brief.key_metrics).length,
    qa: toRecords(brief.notable_qa).length,
    risks: toLines(brief.risks).length,
  };
  const tabs: { key: Tab; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "numbers", label: "Numbers" },
    { key: "qa", label: "Q&A" },
    { key: "risks", label: "Risks" },
  ];

  const ids = [
    brief.nse_symbol ? `NSE ${brief.nse_symbol}` : null,
    brief.scrip_code ? `BSE ${brief.scrip_code}` : null,
  ].filter(Boolean);

  const flash = async (work: () => Promise<void>) => {
    try {
      await work();
      setFailed(false);
    } catch {
      setFailed(true);
      window.setTimeout(() => setFailed(false), 2200);
    }
  };
  const copyMarkdown = () => flash(async () => copy("md", await getMarkdown(brief.id)));
  const downloadMarkdown = () =>
    flash(async () => {
      const text = await getMarkdown(brief.id);
      const url = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `${brief.company}-${brief.quarter}.md`.replace(/[^\w.-]+/g, "_");
      a.click();
      URL.revokeObjectURL(url);
    });

  return (
    <article className="page narrow">
      {back}

      <header className="reader-head">
        <div className="reader-kicker mono">
          <span className="q">{brief.quarter || "Concall"}</span>
          {ids.map((x) => (
            <span key={String(x)}>{x}</span>
          ))}
        </div>
        <h1>{brief.company}</h1>
        <div className="facts mono">
          <span>Call <b>{prettyDate(brief.call_date)}</b></span>
          <span>Filed <b>{prettyDate(brief.filing_date)}</b></span>
          {brief.source && <span>Via <b>{brief.source}</b></span>}
          <TonePill tone={tone} />
        </div>
        <div className="actions">
          <button className="btn" onClick={copyMarkdown}>
            {copied === "md" ? "Copied" : failed ? "Couldn’t copy" : "Copy Markdown"}
          </button>
          <button className="btn" onClick={downloadMarkdown}>Download .md</button>
          {brief.source_url && (
            <a className="btn" href={brief.source_url} target="_blank" rel="noreferrer">Original filing ↗</a>
          )}
        </div>
      </header>

      {toLines(brief.tldr).length > 0 && (
        <section className="tldr" aria-label="In short">
          <span className="tldr-label mono">TL;DR</span>
          <Bullets items={brief.tldr} />
        </section>
      )}

      <div className="tabs" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            className={`tab${tab === t.key ? " on" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
            <span className="tab-n mono">{counts[t.key]}</span>
          </button>
        ))}
      </div>

      <div className="panel" role="tabpanel">
        {tab === "overview" && (
          <>
            {toLines(brief.management_commentary).length > 0 && (
              <Block title="Management commentary"><Bullets items={brief.management_commentary} /></Block>
            )}
            {toLines(brief.guidance).length > 0 && (
              <Block title="Guidance and outlook"><Bullets items={brief.guidance} /></Block>
            )}
            {toRecords(brief.segment_performance).length > 0 && (
              <Block title="Segments"><Segments items={brief.segment_performance} /></Block>
            )}
            {tone?.reason && <Block title="Tone"><p>{tone.reason}</p></Block>}
            {counts.overview === 0 && !tone?.reason && <p className="quiet">Nothing was captured in this section.</p>}
          </>
        )}
        {tab === "numbers" && <MetricsTable items={brief.key_metrics} />}
        {tab === "qa" && <QAList items={brief.notable_qa} />}
        {tab === "risks" &&
          (counts.risks ? <Bullets items={brief.risks} /> : <p className="quiet">No risks were flagged on this call.</p>)}
      </div>
    </article>
  );
}

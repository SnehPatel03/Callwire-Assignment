import { useEffect, useRef, useState } from "react";
import { getActivity, getReplay, startReplay } from "../lib/api";
import { clock } from "../lib/format";
import type { ReplayJob } from "../lib/api";
import type { ActivityEvent } from "../lib/types";

interface Props {
  onActivity: () => void;
}

const HIDDEN = new Set(["ts", "seq", "kind", "company", "source", "reply"]);

function describe(e: ActivityEvent): string {
  if (e.kind === "chunk_done") return `chunk ${e.index}/${e.total}${e.cached ? " (cached)" : ""}`;
  if (e.kind === "merge_done") return e.final ? "final merge" : "merge";
  const detail = Object.entries(e)
    .filter(([k, v]) => !HIDDEN.has(k) && (typeof v === "string" || typeof v === "number" || typeof v === "boolean"))
    .map(([k, v]) => `${k}=${String(v).slice(0, 90)}`)
    .join("  ");
  return detail;
}

export function Replay({ onActivity }: Props) {
  const [days, setDays] = useState(45);
  const [job, setJob] = useState<ReplayJob | null>(null);
  const [replayError, setReplayError] = useState<string | null>(null);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [activityError, setActivityError] = useState<string | null>(null);
  const lastSeq = useRef(0);

  // Poll the activity log while this page is open; tell the app when something new happened.
  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const list = await getActivity();
        if (stop) return;
        const newest = Number(list[list.length - 1]?.seq ?? 0);
        if (lastSeq.current && newest > lastSeq.current) onActivity();
        lastSeq.current = newest;
        setEvents([...list].reverse().slice(0, 150));
        setActivityError(null);
      } catch (e) {
        if (!stop) setActivityError(e instanceof Error ? e.message : "Failed to load activity");
      }
    };
    void tick();
    const timer = window.setInterval(tick, 3000);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, [onActivity]);

  useEffect(() => {
    if (!job?.id || !["scanning", "running"].includes(job.status)) return;
    let stop = false;
    const poll = async () => {
      try {
        const next = await getReplay(job.id);
        if (stop) return;
        setJob(next);
        if (next.status === "complete" || next.status === "failed") onActivity();
      } catch (e) {
        if (!stop) setReplayError(e instanceof Error ? e.message : "Could not read replay status");
      }
    };
    const timer = window.setInterval(() => void poll(), 2000);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, [job?.id, job?.status, onActivity]);

  const run = () => {
    setReplayError(null);
    setJob(null);
    startReplay(days)
      .then(setJob)
      .catch((e: unknown) => setReplayError(e instanceof Error ? e.message : "Could not start replay"));
  };

  const running = job?.status === "scanning" || job?.status === "running";

  return (
    <div className="page narrow">
      <div className="page-head">
        <h1>Replay</h1>
        <p className="quiet">
          Look back over past filings and process any transcripts that aren’t in the wire yet. Only companies on
          your watchlist are processed.
        </p>
      </div>

      <div className="inline-form">
        <label className="label" htmlFor="days">Days to look back</label>
        <input
          id="days"
          className="field short mono"
          type="number"
          min={1}
          max={365}
          value={days}
          onChange={(e) => setDays(Math.max(1, Number(e.target.value) || 1))}
        />
        <button className="btn solid" onClick={run} disabled={running}>
          {running ? "Replay running…" : "Run replay"}
        </button>
      </div>

      {replayError && <div className="notice bad">Replay error: {replayError}</div>}
      {job?.status === "scanning" && <div className="notice">Scanning exchanges for transcripts from the last {job.days} days…</div>}
      {job?.status === "running" && (
        <div className="notice">
          <span>Processing {job.current || "transcripts"}: {job.processed} of {job.found} completed, {job.failed} failed.</span>
          <span>Summaries appear on the Wire as they finish.</span>
        </div>
      )}
      {job?.status === "complete" && (
        <div className={job.failed ? "notice bad" : "notice good"}>
          Replay finished: found {job.found}, processed {job.processed}, failed {job.failed}.
        </div>
      )}
      {job?.status === "failed" && <div className="notice bad">Replay failed: {job.error || "Unknown engine error"}</div>}

      <h2 className="section-label mono">Pipeline activity</h2>
      {activityError && <div className="notice bad">Couldn’t load activity ({activityError}).</div>}
      {!activityError && events.length === 0 && <p className="quiet">Nothing running right now.</p>}
      <ol className="log mono">
        {events.map((e, i) => (
          <li key={e.seq ?? i}>
            <time>{clock(e.ts)}</time>
            <span className={`kind k-${String(e.kind)}`}>{String(e.kind)}</span>
            <span className="log-co">{typeof e.company === "string" ? e.company : ""}</span>
            <span className="log-detail">{describe(e)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

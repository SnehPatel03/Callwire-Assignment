import { useEffect, useRef, useState } from "react";
import { externalSocketUrls, getBrief, listBriefs } from "../lib/api";
import { useCopy } from "../ui/useCopy";

type Test = "idle" | "testing" | "ok" | "failed";
type Sample = { state: "idle" | "loading" | "ready" | "empty" | "failed"; json: string };

export function Stream() {
  const urls = externalSocketUrls();
  const { copied, copy } = useCopy();
  const [test, setTest] = useState<Test>("idle");
  const [sample, setSample] = useState<Sample>({ state: "idle", json: "" });
  const socket = useRef<WebSocket | null>(null);

  useEffect(() => () => socket.current?.close(), []);

  const testConnection = () => {
    socket.current?.close();
    setTest("testing");
    let settled = false;
    const finish = (r: Test) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      setTest(r);
    };
    const timer = window.setTimeout(() => {
      finish("failed");
      socket.current?.close();
    }, 4000);
    try {
      const ws = new WebSocket(urls.briefs);
      socket.current = ws;
      ws.onopen = () => {
        finish("ok");
        ws.close();
      };
      ws.onerror = () => finish("failed");
    } catch {
      finish("failed");
    }
  };

  /** Loads the newest stored brief: every WebSocket message has exactly this shape. */
  const fetchExample = async () => {
    setSample({ state: "loading", json: "" });
    try {
      const rows = await listBriefs();
      if (!rows.length) return setSample({ state: "empty", json: "" });
      const newest = rows.reduce((a, b) => (b.id > a.id ? b : a));
      setSample({ state: "ready", json: JSON.stringify(await getBrief(newest.id), null, 2) });
    } catch {
      setSample({ state: "failed", json: "" });
    }
  };

  const js = `const ws = new WebSocket("${urls.briefs}");
ws.onmessage = (e) => {
  const brief = JSON.parse(e.data);
  console.log(brief.company, brief.quarter, brief.tldr);
};
ws.onclose = () => setTimeout(() => location.reload(), 2000); // naive reconnect`;

  const py = `import asyncio, json, websockets

async def listen():
    async with websockets.connect("${urls.briefs}") as ws:
        async for msg in ws:
            brief = json.loads(msg)
            print("NEW:", brief["company"], brief["quarter"])

asyncio.run(listen())   # pip install websockets`;

  const endpoint = (key: string, label: string, url: string, note: string) => (
    <div className="endpoint">
      <div className="endpoint-head">
        <span className="label">{label}</span>
        <button className="btn small" onClick={() => copy(key, url)}>{copied === key ? "Copied" : "Copy"}</button>
      </div>
      <code className="url mono">{url}</code>
      <p className="quiet">{note}</p>
    </div>
  );

  return (
    <div className="page narrow">
      <div className="page-head">
        <h1>Stream</h1>
        <p className="quiet">
          Point any service at these sockets and it receives each new summary the moment it’s finished. No login
          needed (so keep the engine off the public internet).
        </p>
      </div>

      {endpoint("briefs", "Briefs", urls.briefs, "One JSON message per finished brief. You only get briefs completed after you connect, so list /v1/briefs first to catch up.")}
      {endpoint("activity", "Activity (optional)", urls.activity, "Every pipeline step and raw LLM reply. Recent history is replayed when you connect.")}

      <div className="inline-form">
        <button className="btn solid" onClick={testConnection} disabled={test === "testing"}>
          {test === "testing" ? "Testing…" : "Test connection"}
        </button>
        {test === "ok" && <span className="status good mono">connected</span>}
        {test === "failed" && <span className="status bad mono">couldn’t connect</span>}
      </div>

      <h2 className="section-label mono">Example payload</h2>
      <p className="quiet">Loads the newest stored brief, which has the same structure as every socket message.</p>
      <div className="inline-form">
        <button className="btn" onClick={fetchExample} disabled={sample.state === "loading"}>
          {sample.state === "loading" ? "Loading…" : "Load example"}
        </button>
        {sample.state === "ready" && (
          <button className="btn" onClick={() => copy("sample", sample.json)}>{copied === "sample" ? "Copied" : "Copy JSON"}</button>
        )}
      </div>
      {sample.state === "empty" && <div className="notice">No briefs yet. One will appear here after the first transcript is processed.</div>}
      {sample.state === "failed" && <div className="notice bad">Couldn’t load a brief. Check that the engine is running.</div>}
      {sample.state === "ready" && <pre className="code mono tall">{sample.json}</pre>}

      <h2 className="section-label mono">JavaScript</h2>
      <pre className="code mono">{js}</pre>
      <h2 className="section-label mono">Python</h2>
      <pre className="code mono">{py}</pre>
    </div>
  );
}

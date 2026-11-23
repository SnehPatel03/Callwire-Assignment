import { useCallback, useEffect, useState } from "react";
import { useWire } from "./hooks/useWire";
import { Reader } from "./views/Reader";
import { Replay } from "./views/Replay";
import { Stream } from "./views/Stream";
import { Wire } from "./views/Wire";

type Route = { name: "wire" } | { name: "call"; id: number } | { name: "replay" } | { name: "stream" };

function parse(hash: string): Route {
  const call = hash.match(/^#\/call\/(\d+)/);
  if (call) return { name: "call", id: Number(call[1]) };
  if (hash.startsWith("#/replay")) return { name: "replay" };
  if (hash.startsWith("#/stream")) return { name: "stream" };
  return { name: "wire" };
}

const LINK_TEXT = { live: "live", connecting: "connecting", offline: "offline · retrying" } as const;

export default function App() {
  const wire = useWire(); // lives here so the socket stays open while you move between pages
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash));

  useEffect(() => {
    const onHash = () => {
      setRoute(parse(window.location.hash));
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const { reload } = wire;
  const refresh = useCallback(() => void reload(), [reload]);

  const nav = [
    { name: "wire", href: "#/", label: "Wire" },
    { name: "replay", href: "#/replay", label: "Replay" },
    { name: "stream", href: "#/stream", label: "Stream" },
  ] as const;
  const active = route.name === "call" ? "wire" : route.name;

  return (
    <>
      <header className="masthead">
        <a className="wordmark mono" href="#/" aria-label="Callwire home">
          <span className={`pulse pulse-${wire.link}`} aria-hidden="true" />
          callwire
        </a>
        <nav className="nav" aria-label="Main">
          {nav.map((n) => (
            <a key={n.name} href={n.href} className={active === n.name ? "on" : ""} aria-current={active === n.name ? "page" : undefined}>
              {n.label}
            </a>
          ))}
        </nav>
        <span className={`link-state mono link-${wire.link}`} role="status">{LINK_TEXT[wire.link]}</span>
      </header>

      <main>
        {route.name === "wire" && (
          <Wire rows={wire.rows} loading={wire.loading} error={wire.error} fresh={wire.fresh} onOpen={wire.dismiss} onRetry={refresh} />
        )}
        {route.name === "call" && <Reader key={route.id} id={route.id} />}
        {route.name === "replay" && <Replay onActivity={refresh} />}
        {route.name === "stream" && <Stream />}
      </main>
    </>
  );
}

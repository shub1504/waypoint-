import { useEffect, useState } from "react";
import { get, post } from "../api.js";
import { useUI } from "../ui.js";

/** Not part of the member's app: the controls a presenter uses to fire disruptions. */
export default function DemoPanel() {
  const ui = useUI();
  const [scenarios, setScenarios] = useState([]);
  const [health, setHealth] = useState(null);

  useEffect(() => {
    get("/api/scenarios").then(setScenarios).catch(() => {});
    get("/api/health").then(setHealth).catch(() => {});
  }, []);

  const names = Object.fromEntries(ui.members.map((m) => [m.id, m.name.split(" ")[0]]));
  const run = (s) => {
    ui.setMemberId(s.member); // the scenario belongs to one member; show their account
    post(`/api/simulate/${s.id}`).catch((e) => ui.toast(e.message));
  };

  return (
    <div className="demo-inner">
      <h2>Demo controls</h2>
      <div className="badges">
        <span className={"pill " + (ui.connected ? "good" : "bad")}><i className="dot" /> {ui.connected ? "Live" : "Reconnecting…"}</span>
        {health && <span className="pill muted">bus: {health.bus}</span>}
        {health && <span className="pill muted">db: {health.db}</span>}
      </div>
      <p className="hint">Each button publishes a disruption on the event bus. Waypoint picks it up live and the app shows what it did.</p>
      {scenarios.map((s) => (
        <button key={s.id} className="scenario" onClick={() => run(s)}>
          <span className="slide">{s.slide} · {names[s.member] || s.member}</span>
          {s.title}
        </button>
      ))}
      <button className="reset" onClick={() => post("/api/reset").catch((e) => ui.toast(e.message))}>Reset demo data</button>

      <h2 className="mt">Event stream</h2>
      {ui.events.length === 0 && <p className="hint">Waiting for events…</p>}
      <ul className="stream">
        {ui.events.map((e) => (
          <li key={e.event_id}><b>{e.type.replaceAll("_", " ")}</b><span>{e.booking_id} · {names[e.member_id] || e.member_id}</span></li>
        ))}
      </ul>
    </div>
  );
}

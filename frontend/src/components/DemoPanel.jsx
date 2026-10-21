import { useEffect, useState } from "react";
import { get, post } from "../api.js";
import { useUI } from "../ui.js";
import { KIND_ICON } from "../api.js";
import { Icon } from "./Icons.jsx";

// What can be fired at one booking. The label is what a presenter would say.
const ACTIONS = {
  FLIGHT: [["Flight cancelled", "FLIGHT_CANCELLED", {}], ["Cancelled + 30h delay", "FLIGHT_CANCELLED", { delay_hours: 30 }], ["Missed connection", "MISSED_CONNECTION", { delay_hours: 5 }]],
  TRAIN: [["Train cancelled", "TRAIN_CANCELLED", {}], ["Cancelled + sold out", "TRAIN_CANCELLED", { demand_spike: true }]],
  BUS: [["Bus cancelled", "BUS_CANCELLED", {}]],
  HOTEL: [["Hotel overbooked", "HOTEL_OVERBOOKED", {}]],
};

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
  const custom = !["M001", "M002", "M003"].includes(ui.memberId); // an account added from the app
  const myBookings = ui.trips.filter((t) => t.member.id === ui.memberId)
    .flatMap((t) => t.bookings.filter((b) => b.status === "ACTIVE").map((b) => ({ ...b, trip: t.title })));
  const fire = (b, type, extra) =>
    post("/api/simulate-booking", { booking_id: b.id, type, delay_hours: 0, demand_spike: false, ...extra })
      .catch((e) => ui.toast(e.message));

  const run = (s) => {
    // Built-in scenarios belong to one demo member, so show their account. A new account runs them on itself.
    if (!custom) ui.setMemberId(s.member);
    post(`/api/simulate/${s.id}${custom ? `?member=${ui.memberId}` : ""}`).catch((e) => ui.toast(e.message));
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
      <h2 className="mt0">Disrupt {names[ui.memberId] ? `${names[ui.memberId]}'s` : "my"} bookings</h2>
      {myBookings.length === 0 && <p className="hint">No active bookings on this account. Add one from Profile &gt; New trip.</p>}
      {myBookings.map((b) => (
        <div key={b.id} className="mybk">
          <div className="mybk-h"><Icon name={KIND_ICON[b.kind] || "plane"} size={16} /><span>{b.label}</span></div>
          <div className="mybk-a">
            {(ACTIONS[b.kind] || []).map(([label, type, extra]) => (
              <button key={label} className="chip2" onClick={() => fire(b, type, extra)}>{label}</button>
            ))}
          </div>
        </div>
      ))}

      <h2 className="mt">Ready-made scenarios</h2>
      {scenarios.map((s) => (
        <button key={s.id} className="scenario" onClick={() => run(s)}>
          <span className="slide">{s.slide} · {custom ? names[ui.memberId] : names[s.member] || s.member}</span>
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

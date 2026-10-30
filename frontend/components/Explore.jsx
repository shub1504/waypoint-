import { useCallback, useEffect, useMemo, useState } from "react";
import { KIND_ICON, get, inr, post, signed } from "../api.js";
import { useUI } from "../ui.js";
import { Icon } from "./Icons.jsx";
import Matrix, { optionCols, optionRows } from "./Matrix.jsx";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "ok", label: "Within limit" },
  { id: "cheap", label: "Cheapest" },
  { id: "best", label: "Closest / fastest" },
];

// A booking that was replaced keeps working as an id: follow replaces_id to the live one.
function resolveActive(bookings, id) {
  let b = bookings.find((x) => x.id === id);
  while (b && b.status === "REBOOKED") b = bookings.find((x) => x.replaces_id === b.id);
  return b;
}

export default function Explore() {
  const ui = useUI();
  const bookings = useMemo(
    () => ui.trips.filter((t) => t.member.id === ui.memberId).flatMap((t) => t.bookings),
    [ui.trips, ui.memberId]
  );
  const active = bookings.filter((b) => b.status === "ACTIVE");
  const [selId, setSelId] = useState(null);
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState("all");
  const [picked, setPicked] = useState([]);
  const [err, setErr] = useState("");

  // Which booking is selected: honour a jump from Home, else keep the current one, else the first.
  useEffect(() => {
    const want = ui.exploreTarget?.bookingId || selId;
    const live = want && resolveActive(bookings, want);
    setSelId((live || active[0] || {}).id || null);
  }, [ui.exploreTarget, bookings]); // eslint-disable-line

  const load = useCallback(() => {
    if (!selId) { setData(null); return; }
    setErr("");
    get(`/api/bookings/${selId}/options`).then(setData).catch((e) => setErr(e.message));
  }, [selId]);
  useEffect(() => { setPicked([]); load(); }, [load, ui.trips]);

  const options = useMemo(() => {
    if (!data) return [];
    let o = [...data.options];
    if (filter === "ok") o = o.filter((x) => x.allowed);
    if (filter === "cheap") o.sort((a, b) => a.total_cost - b.total_cost);
    if (filter === "best")
      o.sort((a, b) => data.booking.kind === "HOTEL" ? (a.distance_km ?? 99) - (b.distance_km ?? 99) : (a.depart_in_h ?? 99) - (b.depart_in_h ?? 99));
    return o;
  }, [data, filter]);

  const toggle = (key) => setPicked((p) => (p.includes(key) ? p.filter((k) => k !== key) : p.length >= 3 ? p : [...p, key]));

  const book = (o) =>
    post(`/api/bookings/${data.booking.id}/switch`, { label: o.label })
      .then(() => { ui.closeSheet(); ui.toast(`Booked: ${o.label}`); })
      .catch((e) => ui.toast(e.message));

  const detail = (o) =>
    ui.openSheet(o.label, (
      <div>
        <div className={"verdict " + (o.allowed ? "ok" : "over")}>
          {o.allowed ? "Within your auto-rebook limit" : "Above your auto-rebook limit"}
          <small>{o.reason}</small>
        </div>
        <dl className="facts">
          <dt>Price</dt><dd>{inr(o.total_cost)} <small>({signed(o.delta)} vs current)</small></dd>
          {o.extra_leg_cost ? <><dt>Includes cab</dt><dd>{inr(o.extra_leg_cost)}</dd></> : null}
          {o.area ? <><dt>Area</dt><dd>{o.area}, {o.distance_km} km from {data.purpose}</dd></> : null}
          {o.relevance != null ? <><dt>Relevance</dt><dd>{o.relevance.toFixed(2)} of 1.00</dd></> : null}
          {o.depart_in_h != null ? <><dt>Leaves in</dt><dd>{Math.round(o.depart_in_h)}h</dd></> : null}
          {o.duration_h != null ? <><dt>Journey</dt><dd>{o.duration_h}h</dd></> : null}
          <dt>How</dt><dd>{o.via}</dd>
        </dl>
        <button className={"btn " + (o.allowed ? "primary" : "warnbtn")} onClick={() => book(o)}>
          {o.allowed ? "Book this option" : "Book anyway (I approve the extra cost)"}
        </button>
        <p className="sub">This replaces your current booking. Your old one moves to Profile &gt; Old.</p>
      </div>
    ));

  const compare = () => {
    const chosen = data.options.filter((o) => picked.includes(o.key));
    ui.openSheet(`Compare ${chosen.length} options`, (
      <Matrix cols={optionCols(chosen)} rows={optionRows(data.booking.kind, data.booking.amount)} />
    ));
  };

  if (active.length === 0) return <div className="empty"><h3>Nothing to explore</h3><p>This account has no active bookings.</p></div>;

  return (
    <div>
      <div className="chips" role="tablist">
        {active.map((b) => (
          <button key={b.id} role="tab" aria-selected={b.id === selId} className={"chip2 " + (b.id === selId ? "on" : "")}
            onClick={() => { setSelId(b.id); setFilter("all"); }}>
            <Icon name={KIND_ICON[b.kind] || "plane"} size={16} />{b.kind === "HOTEL" ? "Hotel" : `${b.origin} → ${b.destination}`}
          </button>
        ))}
      </div>

      {err && <div className="error">{err}</div>}
      {data && (
        <>
          <div className="summary">
            <div><small>Current</small><b>{inr(data.booking.amount)}</b></div>
            <div><small>Auto limit</small><b>{inr(data.limit)}</b></div>
            <div><small>Trip pool</small><b>{inr(data.pool_credit)}</b></div>
          </div>
          <p className="sub pad">{data.booking.label}</p>

          <div className="chips small" role="group" aria-label="Filter">
            {FILTERS.map((f) => (
              <button key={f.id} className={"chip2 " + (filter === f.id ? "on" : "")} onClick={() => setFilter(f.id)}>{f.label}</button>
            ))}
          </div>

          {options.length === 0 && <div className="empty"><p>No options match this filter.</p></div>}
          <div className="grid">
            {options.map((o, i) => (
              <div key={o.key} className={"tile " + (o.allowed ? "" : "over")}>
                <button className="tmedia" onClick={() => detail(o)} aria-label={`Open ${o.label}`}>
                  <Icon name={KIND_ICON[o.kind] || "plane"} size={26} />
                  <b>{inr(o.total_cost)}</b>
                  {i === 0 && filter === "all" && o.allowed && <em className="tag good">Best match</em>}
                  {!o.allowed && <em className="tag warn">Above limit</em>}
                </button>
                <label className="pick"><input type="checkbox" checked={picked.includes(o.key)} onChange={() => toggle(o.key)} aria-label={`Compare ${o.label}`} /><span /></label>
                <div className="tinfo">
                  <p>{o.label}</p>
                  <small>
                    {o.area ? `${o.distance_km} km · ${o.area}` : `leaves in ${Math.round(o.depart_in_h)}h · ${o.duration_h}h`}
                  </small>
                  <small className={o.delta > 0 ? "up" : "down"}>{signed(o.delta)} vs current</small>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {picked.length >= 2 && (
        <button className="fab" onClick={compare}><Icon name="table" size={18} /> Compare ({picked.length})</button>
      )}
      {picked.length === 1 && <div className="hintbar">Select one more to compare (up to 3)</div>}
    </div>
  );
}

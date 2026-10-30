import { useState } from "react";
import { EVENT_LABEL, KIND_ICON, STATUS, ago, inr, post } from "../api.js";
import { useUI } from "../ui.js";
import { Icon } from "./Icons.jsx";
import Avatar from "./Avatar.jsx";
import Matrix, { optionCols, optionRows } from "./Matrix.jsx";
import { TripSheet } from "./TripCard.jsx";

const WAITING = ["NEEDS_APPROVAL", "FALLBACK_OPTIONS"];
const FILTERS = [
  { id: "all", label: "All", test: () => true },
  { id: "action", label: "Needs action", test: (d) => WAITING.includes(d.status) },
  { id: "auto", label: "Auto-rebooked", test: (d) => d.status === "AUTO_BOOKED" },
  { id: "done", label: "Resolved", test: (d) => !WAITING.includes(d.status) && d.status !== "AUTO_BOOKED" },
];
const KINDS = [
  { k: "FLIGHT", label: "Flights", icon: "plane" },
  { k: "HOTEL", label: "Hotels", icon: "bed" },
  { k: "TRAIN", label: "Trains", icon: "train" },
  { k: "BUS", label: "Buses", icon: "bus" },
];

const short = (n) => (n >= 1000 ? "\u20b9" + (Math.round(n / 100) / 10).toString().replace(/\.0$/, "") + "k" : "\u20b9" + Math.round(n));
const pctOf = (a, b) => (b > 0 ? Math.round((a / b) * 100) : 0);
const tripIcon = (t) => (t.bookings.some((b) => b.kind === "TRAIN") ? "train" : "plane");
const nameShort = (n = "") => { const [a, b] = n.split(" "); return b ? `${a} ${b[0]}.` : a; };

export default function Home() {
  const ui = useUI();
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const myTrips = ui.trips.filter((t) => t.member.id === ui.memberId);
  const mine = ui.decisions.filter((d) => d.member_id === ui.memberId);
  const bookingsById = Object.fromEntries(ui.trips.flatMap((t) => t.bookings.map((b) => [b.id, b])));

  const active = myTrips.flatMap((t) => t.bookings.filter((b) => b.status === "ACTIVE"));
  const committed = active.reduce((n, b) => n + b.amount, 0);
  const envelope = myTrips.reduce((n, t) => n + t.envelope, 0);
  const pool = myTrips.reduce((n, t) => n + (t.pool_credit || 0), 0);
  const waiting = mine.filter(FILTERS[1].test).length;
  const auto = mine.filter(FILTERS[2].test).length;
  const resolved = mine.length - waiting - auto;
  const byKind = KINDS.map((x) => ({ ...x, amount: active.filter((b) => b.kind === x.k).reduce((n, b) => n + b.amount, 0) })).filter((x) => x.amount > 0);

  const needle = q.trim().toLowerCase();
  const shown = mine
    .filter(FILTERS.find((f) => f.id === filter).test)
    .filter((d) => !needle || [d.chosen_label, d.reasoning, d.kind, EVENT_LABEL[d.event_type]].join(" ").toLowerCase().includes(needle));

  const whole = Math.floor(committed);
  const dec = String(Math.round((committed - whole) * 100)).padStart(2, "0");
  const openTrip = (t) => ui.openSheet(t.title, <TripSheet trip={t} />);

  return (
    <div className="dash">
      <div className="mchips" role="tablist" aria-label="Travellers">
        <button className="mchip add" onClick={ui.openAccounts} aria-label="Add or switch account"><Icon name="plus" size={18} /></button>
        {ui.members.map((m) => (
          <button key={m.id} role="tab" aria-selected={m.id === ui.memberId} className={"mchip " + (m.id === ui.memberId ? "on" : "")} onClick={() => ui.setMemberId(m.id)}>
            <Avatar m={m} cls="xs" />{nameShort(m.name)}
          </button>
        ))}
      </div>

      <h1 className="bigtitle">Your trips</h1>

      <div className="hero">
        <div className="hl">
          <b>Committed</b>
          <div className="hnum">{inr(whole)}<em>.{dec}</em>
            <span className="pillr">{pctOf(committed, envelope)}%</span>
            <span className="pillr alt">{inr(pool)} pool</span>
          </div>
          <p className="hsub">vs budget {inr(envelope)} · {active.length} bookings watched</p>
        </div>
        <div className="hcards">
          <div className="hc"><span>Handled</span><b>{auto + resolved}</b><small>of {mine.length} alerts</small></div>
          <button className="hc dark" onClick={() => ui.go("chat")}><span>Ask Waypoint</span><b>{waiting}</b><small>waiting on you</small><i className="hgo"><Icon name="chevron" size={16} /></i></button>
        </div>
      </div>

      <div className="strip" aria-label="Trips">
        {myTrips.length === 0 && <span className="spill empty">No trips yet</span>}
        {myTrips.map((t) => (
          <button key={t.id} className="spill" onClick={() => openTrip(t)}>
            <span className="sic"><Icon name={tripIcon(t)} size={18} /></span>
            <b>{inr(t.spent)}</b><span className="p">{pctOf(t.spent, committed)}%</span>
          </button>
        ))}
      </div>

      <div className="panels">
        <section className="panel">
          <div className="phd"><span className="fbtn"><Icon name="grid" size={16} /> By type</span><span className="fbtn ghost">{inr(committed)}</span></div>
          <ul className="rows">
            {byKind.length === 0 && <li className="lrow"><span className="lname">No active bookings</span></li>}
            {byKind.map((x) => (
              <li key={x.k} className="lrow">
                <span className="lic"><Icon name={x.icon} size={18} /></span>
                <span className="lname">{x.label}</span><b>{inr(x.amount)}</b><span className="lpct">{pctOf(x.amount, committed)}%</span>
              </li>
            ))}
          </ul>
        </section>
        <BudgetBars trips={myTrips} onOpen={openTrip} />
      </div>

      <div className="actrow">
        <section className="alertc">
          <h4>Alerts</h4>
          <dl>
            <div><dt>Needs action</dt><dd>{waiting}</dd></div>
            <div><dt>Auto-rebooked</dt><dd>{auto}</dd></div>
            <div><dt>Resolved</dt><dd>{resolved}</dd></div>
          </dl>
        </section>
        <div className="actmain">
          <div className="acth">
            <h3>Activity</h3>
            <label className="search"><Icon name="search" size={16} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search alerts" aria-label="Search alerts" /></label>
            <div className="segc" role="tablist" aria-label="Filter activity">
              {FILTERS.map((f) => (
                <button key={f.id} role="tab" aria-selected={filter === f.id} className={filter === f.id ? "on" : ""} onClick={() => setFilter(f.id)}>{f.label}</button>
              ))}
            </div>
          </div>
          <div className="feed">
            {mine.length === 0 ? (
              <div className="empty">
                <h3>Your feed is quiet</h3>
                <p>When a flight, train or hotel is disrupted, Waypoint posts what it did right here. Trigger one from the Demo panel to see it.</p>
                <button className="btn" onClick={ui.openDemo}><Icon name="flask" size={18} /> Open demo controls</button>
              </div>
            ) : shown.length === 0 ? (
              <div className="empty"><p>Nothing matches.</p></div>
            ) : (
              shown.map((d) => <Post key={d.id} d={d} orig={bookingsById[d.booking_id]} />)
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/** One hatched bar per trip: the bar is the budget, the white fill is what is committed (red when over). */
function BudgetBars({ trips, onOpen }) {
  const list = trips.slice(0, 6);
  const top = Math.max(1, ...list.map((t) => Math.max(t.envelope, t.spent))) * 1.18;
  return (
    <section className="panel">
      <div className="phd"><span className="fbtn"><Icon name="chart" size={16} /> Budget</span><span className="fbtn ghost">{trips.length} {trips.length === 1 ? "trip" : "trips"}</span></div>
      <div className="hbars">
        {list.length === 0 && <p className="pcap">No trips yet.</p>}
        {list.map((t) => {
          const full = Math.max(t.envelope, t.spent);
          return (
            <button key={t.id} className="hb" onClick={() => onOpen(t)} aria-label={`${t.title}: ${inr(t.spent)} of ${inr(t.envelope)}`}>
              <span className="hbar" style={{ "--h": (full / top) * 100 + "%", "--f": (t.spent / full) * 100 + "%" }}>
                <span className={"hfill " + (t.spent > t.envelope ? "over" : "")} />
                <i className="hico"><Icon name={tripIcon(t)} size={17} /></i>
                <span className="htip">{short(t.spent)} / {short(t.envelope)}</span>
              </span>
            </button>
          );
        })}
      </div>
      <p className="pcap">Committed vs budget<br /><b>by trip</b></p>
    </section>
  );
}

function LimitBar({ d }) {
  const max = Math.max(d.ceiling, d.chosen_amount || 0) * 1.08;
  const over = d.chosen_amount > d.ceiling;
  return (
    <div className="limit">
      <div className="track">
        <div className={"fill " + (over ? "over" : "")} style={{ width: ((d.chosen_amount || 0) / max) * 100 + "%" }} />
        <i className="mark orig" style={{ left: (d.original_amount / max) * 100 + "%" }} title="original" />
        <i className="mark lim" style={{ left: (d.ceiling / max) * 100 + "%" }} title="limit" />
      </div>
      <div className="row small"><span>original {inr(d.original_amount)}</span><span>limit {inr(d.ceiling)}</span></div>
    </div>
  );
}

function Post({ d, orig }) {
  const ui = useUI();
  const [more, setMore] = useState(false);
  const st = STATUS[d.status] || { label: d.status, tone: "muted" };
  const route = orig && orig.origin && orig.destination ? `${orig.origin} → ${orig.destination}` : null;
  const fallback = d.status === "FALLBACK_OPTIONS";
  const cancelled = d.status === "TRIP_CANCELLED" || d.status === "BOOKING_CANCELLED";
  const act = (fn) => fn().catch((e) => ui.toast(e.message));

  const compare = () =>
    ui.openSheet("Options compared", (
      <div>
        <p className="sub">Every option the agent considered. Highlighted column is the pick.</p>
        <Matrix cols={optionCols(d.options, d.chosen_label)} rows={optionRows(d.kind, d.original_amount)} />
      </div>
    ));

  return (
    <article className="post">
      <header className="phead">
        <span className="avatar brand">W</span>
        <div className="who">
          <b>Waypoint</b>
          <small>{EVENT_LABEL[d.event_type] || d.event_type} · {ago(d.created_at)}</small>
        </div>
        <span className={"chip " + st.tone}>{st.label}</span>
      </header>

      <div className={"media " + st.tone}>
        <div className="mtop"><Icon name={KIND_ICON[d.kind] || "plane"} size={18} />
          <span>{d.kind}{route ? ` · ${route}` : ""}</span>
          {d.latency_ms > 0 && <em>{d.latency_ms} ms</em>}</div>
        {cancelled ? (
          <div className="mbody"><div className="big">{d.kind === "TRIP" ? "Trip cancelled" : "Booking cancelled"}</div>
            <div className="muted">{d.chosen_label} expected back of {inr(d.original_amount)}</div></div>
        ) : fallback ? (
          <div className="mbody"><div className="big">Sold out</div><div className="muted">No tickets from {orig?.origin}. Pick an alternative below.</div></div>
        ) : (
          <div className="mbody">
            <div className="ba"><small>Before</small><s>{orig ? orig.label.replace(/ \(\d night.*\)/, "") : "—"}</s></div>
            <div className="ba"><small>{d.status === "NEEDS_APPROVAL" ? "Best option" : "After"}</small><b>{d.chosen_label || "—"}</b></div>
            <div className="price">{inr(d.chosen_amount)}</div>
            <LimitBar d={d} />
          </div>
        )}
      </div>

      {d.status === "NEEDS_APPROVAL" && (
        <div className="cta">
          <button className="btn primary" onClick={() => act(() => post(`/api/decisions/${d.id}/approve`))}>Approve {inr(d.chosen_amount)}</button>
          <button className="btn" onClick={() => act(() => post(`/api/decisions/${d.id}/decline`))}>Decline</button>
        </div>
      )}
      {fallback && (
        <div className="cta col">
          {d.options.length === 0 && <p className="sub">No alternatives found. Support will contact you.</p>}
          {d.options.map((o, i) => (
            <button key={i} className="opt" onClick={() => act(() => post(`/api/decisions/${d.id}/choose/${i}`))}>
              <span>{o.label}</span><b>{inr(o.total_cost)}</b>
              <small className={o.allowed ?? o.within_guardrail ? "ok" : "over"}>{(o.allowed ?? o.within_guardrail) ? "within your limit" : "above your limit"} · {o.via}</small>
            </button>
          ))}
          <button className="btn" onClick={() => act(() => post(`/api/decisions/${d.id}/decline`))}>None of these</button>
        </div>
      )}

      {!cancelled && <div className="actions">
        <button onClick={compare} aria-label="Compare options"><Icon name="table" /><span>Compare</span></button>
        <button onClick={() => ui.go("explore", { bookingId: d.booking_id })} aria-label="Explore more options"><Icon name="compass" /><span>More options</span></button>
        <button onClick={() => ui.go("chat")} aria-label="Ask in chat"><Icon name="chat" /><span>Ask why</span></button>
      </div>}

      <p className={"caption " + (more ? "open" : "")}>
        <b>Waypoint</b> {d.reasoning}
        {!more && d.reasoning.length > 140 && <button className="link" onClick={() => setMore(true)}> more</button>}
      </p>
    </article>
  );
}
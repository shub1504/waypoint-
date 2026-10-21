import { useState } from "react";
import { EVENT_LABEL, KIND_ICON, STATUS, ago, inr, post } from "../api.js";
import { useUI } from "../ui.js";
import { Icon } from "./Icons.jsx";
import Matrix, { optionCols, optionRows } from "./Matrix.jsx";
import { TripSheet } from "./TripCard.jsx";

export default function Home() {
  const ui = useUI();
  const myTrips = ui.trips.filter((t) => t.member.id === ui.memberId);
  const mine = ui.decisions.filter((d) => d.member_id === ui.memberId);
  const bookingsById = Object.fromEntries(ui.trips.flatMap((t) => t.bookings.map((b) => [b.id, b])));

  const active = myTrips.flatMap((t) => t.bookings.filter((b) => b.status === "ACTIVE"));
  const committed = active.reduce((n, b) => n + b.amount, 0);
  const pool = myTrips.reduce((n, t) => n + (t.pool_credit || 0), 0);

  return (
    <div>
      <div className="hsum" aria-label="Summary">
        <div><small>Watching</small><b>{active.length}</b><span>bookings</span></div>
        <div><small>Committed</small><b>{inr(committed)}</b><span>right now</span></div>
        <div><small>Trip pool</small><b>{inr(pool)}</b><span>saved for disruptions</span></div>
      </div>
      <div className="stories" role="list">
        {myTrips.map((t) => {
          const waiting = mine.some((d) => d.trip_id === t.id && ["NEEDS_APPROVAL", "FALLBACK_OPTIONS"].includes(d.status));
          return (
            <button key={t.id} className="story" role="listitem" onClick={() => ui.openSheet(t.title, <TripSheet trip={t} />)}>
              <span className={"ring " + (waiting ? "alert" : "")}>
                <span className="inner"><Icon name={t.bookings.some((b) => b.kind === "TRAIN") ? "train" : "plane"} size={24} /></span>
              </span>
              <span className="cap">{t.title.split(" ")[0]}</span>
            </button>
          );
        })}
      </div>

      {mine.length === 0 ? (
        <div className="empty">
          <h3>Your feed is quiet</h3>
          <p>When a flight, train or hotel is disrupted, Waypoint posts what it did right here. Trigger one from the Demo panel to see it.</p>
          <button className="btn" onClick={ui.openDemo}><Icon name="flask" size={18} /> Open demo controls</button>
        </div>
      ) : (
        mine.map((d) => <Post key={d.id} d={d} orig={bookingsById[d.booking_id]} />)
      )}
    </div>
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

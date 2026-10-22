import { KIND_ICON, inr } from "../api.js";
import { Icon } from "./Icons.jsx";

/** Budget bar + booking list for one trip. Shown in a sheet (Home stories, right rail). */
export function TripSheet({ trip }) {
  const cap = trip.envelope * 1.7;
  return (
    <div>
      <p className="sub">{trip.purpose}</p>
      <div className="bar"><div className="fill" style={{ width: Math.min(100, (trip.spent / cap) * 100) + "%" }} />
        <div className="env" style={{ left: (trip.envelope / cap) * 100 + "%" }} /></div>
      <div className="row small"><span>Committed {inr(trip.spent)}</span><span>Original budget {inr(trip.envelope)}</span></div>
      {trip.pool_credit > 0 && <div className="pool">Trip pool: {inr(trip.pool_credit)} saved</div>}
      <ul className="blist">
        {trip.bookings.map((b) => (
          <li key={b.id} className={b.status === "REBOOKED" ? "old" : ""}>
            <Icon name={KIND_ICON[b.kind] || "plane"} size={18} /><span>{b.label}{b.status === "ACTIVE" && b.auto_limit != null && <small className="lim" style={{ display: "block" }}>Auto limit {inr(b.auto_limit)} ({inr(b.baseline_amount)} × {b.multiplier})</small>}</span><b>{inr(b.amount)}</b>
          </li>
        ))}
      </ul>
    </div>
  );
}

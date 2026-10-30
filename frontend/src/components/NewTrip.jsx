import { useState } from "react";
import { inr, post } from "../api.js";
import { useUI } from "../ui.js";
import { Icon } from "./Icons.jsx";

const blankT = () => ({ kind: "FLIGHT", origin: "", destination: "", name: "", price: "" });
const blankH = () => ({ name: "", area: "", distance_km: "1", nights: "1", price_per_night: "" });
const KINDS = [["FLIGHT", "Flight"], ["TRAIN", "Train"], ["BUS", "Bus"]];
const PURPOSES = ["temple", "business", "monument", "leisure"];

const EXAMPLE = {
  title: "Ujjain darshan", destination: "Ujjain", purpose_type: "temple", purpose_place: "Mahakaleshwar Temple",
  transports: [
    { kind: "FLIGHT", origin: "DEL", destination: "IDR", name: "IndiGo 6E-2031", price: "4200" },
    { kind: "TRAIN", origin: "UJN", destination: "NDLS", name: "Narmada Express 12912", price: "1800" },
  ],
  hotels: [{ name: "Hotel Ujjain Residency", area: "Temple Area", distance_km: "0.4", nights: "2", price_per_night: "2000" }],
};

/** Enter a trip you already booked: where from, where to, tickets and hotels with their prices. */
export default function NewTrip({ onDone }) {
  const ui = useUI();
  const [f, setF] = useState({ title: "", destination: "", purpose_type: "temple", purpose_place: "" });
  const [ts, setTs] = useState([blankT()]);
  const [hs, setHs] = useState([]);
  const [busy, setBusy] = useState(false);

  const setT = (i, k, v) => setTs((a) => a.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  const setH = (i, k, v) => setHs((a) => a.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  const num = (v) => Number(v) || 0;
  const total = ts.reduce((s, t) => s + num(t.price), 0) + hs.reduce((s, h) => s + num(h.price_per_night) * Math.max(1, num(h.nights)), 0);

  const fill = () => {
    setF({ title: EXAMPLE.title, destination: EXAMPLE.destination, purpose_type: EXAMPLE.purpose_type, purpose_place: EXAMPLE.purpose_place });
    setTs(EXAMPLE.transports); setHs(EXAMPLE.hotels);
  };

  const submit = async (e) => {
    e.preventDefault();
    const transports = ts.filter((t) => t.origin || t.destination || t.price);
    const hotels = hs.filter((h) => h.name || h.price_per_night);
    if (!f.destination.trim()) return ui.toast("Where are you going? Add a destination.");
    if (transports.some((t) => !t.origin.trim() || !t.destination.trim() || num(t.price) <= 0))
      return ui.toast("Every ticket needs a from, a to and a price.");
    if (hotels.some((h) => !h.name.trim() || num(h.price_per_night) <= 0))
      return ui.toast("Every hotel needs a name and a price per night.");
    if (!transports.length && !hotels.length) return ui.toast("Add at least one ticket or hotel you have booked.");
    setBusy(true);
    try {
      await post("/api/trips", {
        member_id: ui.memberId, ...f,
        transports: transports.map((t) => ({ ...t, price: num(t.price) })),
        hotels: hotels.map((h) => ({ ...h, distance_km: num(h.distance_km), nights: Math.max(1, Math.round(num(h.nights))), price_per_night: num(h.price_per_night) })),
      });
      ui.toast("Trip added. Fire a disruption from Demo controls to see Waypoint work on it.");
      onDone && onDone();
    } catch (err) { ui.toast(err.message); } finally { setBusy(false); }
  };

  const F = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));

  return (
    <form className="nt" onSubmit={submit}>
      <div className="ntop">
        <p className="sub">Tell Waypoint what you have already booked. It uses these prices to set your limits, then looks after the trip.</p>
        <button type="button" className="link" onClick={fill}>Fill an example</button>
      </div>

      <section>
        <h4>Trip</h4>
        <div className="two">
          <label>Destination city<input className="text" value={f.destination} onChange={F("destination")} placeholder="Ujjain" /></label>
          <label>Trip name (optional)<input className="text" value={f.title} onChange={F("title")} placeholder="Ujjain darshan" /></label>
        </div>
        <label>Why are you going?
          <div className="seg" role="radiogroup" aria-label="Purpose">
            {PURPOSES.map((p) => <button type="button" key={p} role="radio" aria-checked={f.purpose_type === p} className={f.purpose_type === p ? "on" : ""} onClick={() => setF((x) => ({ ...x, purpose_type: p }))}>{p}</button>)}
          </div>
        </label>
        <label>Place you want to be near (optional)<input className="text" value={f.purpose_place} onChange={F("purpose_place")} placeholder="Mahakaleshwar Temple" /></label>
      </section>

      <section>
        <h4>Tickets you booked</h4>
        {ts.map((t, i) => (
          <div className="item" key={i}>
            <div className="seg" role="radiogroup" aria-label="Ticket type">
              {KINDS.map(([k, l]) => <button type="button" key={k} role="radio" aria-checked={t.kind === k} className={t.kind === k ? "on" : ""} onClick={() => setT(i, "kind", k)}>{l}</button>)}
            </div>
            <div className="two">
              <label>From<input className="text" value={t.origin} onChange={(e) => setT(i, "origin", e.target.value)} placeholder="DEL" /></label>
              <label>To<input className="text" value={t.destination} onChange={(e) => setT(i, "destination", e.target.value)} placeholder="IDR" /></label>
            </div>
            <div className="two">
              <label>Name / number<input className="text" value={t.name} onChange={(e) => setT(i, "name", e.target.value)} placeholder="IndiGo 6E-2031" /></label>
              <label>Price paid (₹)<input className="text" inputMode="numeric" value={t.price} onChange={(e) => setT(i, "price", e.target.value)} placeholder="4200" /></label>
            </div>
            {ts.length > 1 && <button type="button" className="link rm" onClick={() => setTs((a) => a.filter((_, j) => j !== i))}>Remove ticket</button>}
          </div>
        ))}
        <button type="button" className="btn add" onClick={() => setTs((a) => [...a, blankT()])}><Icon name="plus" size={16} /> Add another ticket</button>
        <p className="sub">Airport and station codes (DEL, BOM, UJN, NDLS) work best. Other places work too.</p>
      </section>

      <section>
        <h4>Hotels you booked</h4>
        {hs.map((h, i) => (
          <div className="item" key={i}>
            <div className="two">
              <label>Hotel name<input className="text" value={h.name} onChange={(e) => setH(i, "name", e.target.value)} placeholder="Hotel Ujjain Residency" /></label>
              <label>Area<input className="text" value={h.area} onChange={(e) => setH(i, "area", e.target.value)} placeholder="Temple Area" /></label>
            </div>
            <div className="three">
              <label>Km from your place<input className="text" inputMode="decimal" value={h.distance_km} onChange={(e) => setH(i, "distance_km", e.target.value)} /></label>
              <label>Nights<input className="text" inputMode="numeric" value={h.nights} onChange={(e) => setH(i, "nights", e.target.value)} /></label>
              <label>Per night (₹)<input className="text" inputMode="numeric" value={h.price_per_night} onChange={(e) => setH(i, "price_per_night", e.target.value)} placeholder="2000" /></label>
            </div>
            <button type="button" className="link rm" onClick={() => setHs((a) => a.filter((_, j) => j !== i))}>Remove hotel</button>
          </div>
        ))}
        <button type="button" className="btn add" onClick={() => setHs((a) => [...a, blankH()])}><Icon name="plus" size={16} /> Add a hotel</button>
      </section>

      <div className="ntotal"><span>Trip budget</span><b>{inr(total)}</b></div>
      <button className="btn primary" type="submit" disabled={busy}>Create trip</button>
    </form>
  );
}

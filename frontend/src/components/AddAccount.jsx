import { useState } from "react";
import { post } from "../api.js";
import { useUI } from "../ui.js";

function Choice({ label, value, options, onChange }) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button type="button" key={o} role="radio" aria-checked={value === o} className={value === o ? "on" : ""} onClick={() => onChange(o)}>{o}</button>
      ))}
    </div>
  );
}

/** Sign-up form: creates a new member with a starter trip so every demo scenario works for them. */
export default function AddAccount() {
  const ui = useUI();
  const [f, setF] = useState({ name: "", email: "", phone: "", home_city: "Delhi", budget_level: "medium", alert_channel: "Push" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const ok = f.name.trim() && f.email.includes("@");

  const submit = async (e) => {
    e.preventDefault();
    if (!ok || busy) return;
    setBusy(true);
    try {
      const m = await post("/api/members", f);
      ui.setMembers((ms) => (ms.some((x) => x.id === m.id) ? ms : [...ms, m]));
      ui.setMemberId(m.id);
      ui.closeSheet();
      ui.go("home");
      ui.toast(`Welcome, ${m.name.split(" ")[0]}! Your starter trip is ready. Try a disruption from Demo controls.`);
    } catch (err) {
      ui.toast(err.message);
    } finally { setBusy(false); }
  };

  return (
    <form className="addform" onSubmit={submit}>
      <label>Full name<input className="text" value={f.name} onChange={set("name")} autoFocus /></label>
      <label>Email<input className="text" type="email" value={f.email} onChange={set("email")} /></label>
      <label>Phone<input className="text" type="tel" value={f.phone} onChange={set("phone")} /></label>
      <label>Home city<input className="text" value={f.home_city} onChange={set("home_city")} /></label>
      <div><span className="lab">Budget comfort</span><Choice label="Budget comfort" value={f.budget_level} options={["low", "medium", "high"]} onChange={(v) => setF((x) => ({ ...x, budget_level: v }))} /></div>
      <div><span className="lab">Alert me by</span><Choice label="Alert channel" value={f.alert_channel} options={["Push", "SMS", "Email"]} onChange={(v) => setF((x) => ({ ...x, alert_channel: v }))} /></div>
      <p className="sub">You get a starter trip (flight, hotel, train) and past temple stays, so you can fire any disruption on this account.</p>
      <button className="btn primary" type="submit" disabled={!ok || busy}>Create account</button>
    </form>
  );
}

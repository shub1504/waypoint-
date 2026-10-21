import { useEffect, useState } from "react";
import { get, inr, post } from "../api.js";
import { useUI } from "../ui.js";

/** Cancel a whole trip (booking = undefined) or one booking. Waypoint acts on the reason you give. */
export default function CancelSheet({ trip, booking }) {
  const ui = useUI();
  const [reasons, setReasons] = useState([]);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const body = { trip_id: trip.id, booking_id: booking ? booking.id : null, reason };
  const needsWords = reason === "other" && !note.trim();

  useEffect(() => { get("/api/cancel/reasons").then(setReasons).catch(() => {}); }, []);
  useEffect(() => {
    if (!reason) { setPlan(null); return; }
    let live = true;
    post("/api/cancel/preview", { ...body, note: note || "x" }).then((p) => live && setPlan(p)).catch((e) => live && setPlan({ ok: false, message: e.message }));
    return () => { live = false; };
  }, [reason]); // eslint-disable-line

  const confirm = async () => {
    setBusy(true);
    try {
      await post("/api/cancel", { ...body, note });
      ui.closeSheet();
    } catch (e) { ui.toast(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="cancel">
      <p className="sub">{booking ? booking.label : `${trip.title}: every active booking in this trip`}</p>
      <h4 className="lab">Why are you cancelling?</h4>
      <div className="reasons" role="radiogroup" aria-label="Reason">
        {reasons.map((r) => (
          <button key={r.id} role="radio" aria-checked={reason === r.id} className={"reason " + (reason === r.id ? "on" : "")} onClick={() => setReason(r.id)}>
            <b>{r.label}</b><small>{r.does}</small>
          </button>
        ))}
      </div>

      {reason && (
        <>
          <input className="text" value={note} maxLength={140} onChange={(e) => setNote(e.target.value)}
            placeholder={reason === "other" ? "Tell us in a few words why (required)" : "Add a note (optional)"} aria-label="Reason in your words" autoFocus={reason === "other"} />
          {reason === "other" && <small className="muted">Short is fine, for example: "boss moved the meeting". Waypoint remembers it.</small>}
          {plan && (
            <div className={"plan " + (plan.ok ? "" : "bad")}>
              <b>{plan.ok ? "What will happen" : "Not possible"}</b>
              <p>{plan.message}</p>
              {plan.ok && plan.items && plan.items.length > 0 && (
                <ul>
                  {plan.items.map((i) => (
                    <li key={i.booking_id}><span>{i.label}<small>{i.note}</small></span><b>{inr(i.refund)}</b></li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <button className="btn primary" disabled={busy || !plan || !plan.ok || needsWords} onClick={confirm}>
            {reason === "better_option" ? "Swap to the cheaper option" : booking ? "Cancel this booking" : "Cancel the whole trip"}
          </button>
        </>
      )}
      <p className="sub">Waypoint will notify you on your chosen channel once it is done.</p>
    </div>
  );
}

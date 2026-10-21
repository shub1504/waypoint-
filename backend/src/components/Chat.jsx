import { useEffect, useMemo, useRef, useState } from "react";
import { STATUS, get, inr, post } from "../api.js";
import { useUI } from "../ui.js";
import { Icon } from "./Icons.jsx";

const START = ["How much budget is left?", "What is my auto-rebook limit?", "Why did you pick that?", "Show my bookings"];
const START_ADK = ["How much budget is left?", "Show cheaper options for my hotel", "Cancel my trip, my plans changed", "Why did you pick that?"];

export default function Chat() {
  const ui = useUI();
  const me = ui.members.find((m) => m.id === ui.memberId);
  const [typed, setTyped] = useState({}); // per member: [{from, text, t}]
  const [suggest, setSuggest] = useState(START);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [engine, setEngine] = useState("rules");
  const end = useRef(null);
  useEffect(() => { get("/api/health").then((h) => { setEngine(h.chat || "rules"); if (h.chat === "adk") setSuggest(START_ADK); }).catch(() => {}); }, []);

  const thread = useMemo(() => {
    const own = typed[ui.memberId] || [];
    const decisions = ui.decisions
      .filter((d) => d.member_id === ui.memberId)
      .map((d) => ({ kind: "decision", d, t: new Date(d.created_at).getTime() }));
    const hello = { kind: "text", from: "bot", t: 0, text: `Hi ${me ? me.name.split(" ")[0] : ""}, I'm Waypoint. I'll message you here whenever something on your trip changes. You can also ask me about your budget, limits or bookings.` };
    return [hello, ...own.map((m) => ({ kind: "text", ...m })), ...decisions].sort((a, b) => a.t - b.t);
  }, [typed, ui.decisions, ui.memberId, me]);

  useEffect(() => { end.current && end.current.scrollIntoView({ block: "end" }); }, [thread.length, busy]);

  const add = (m) => setTyped((s) => ({ ...s, [ui.memberId]: [...(s[ui.memberId] || []), { ...m, t: Date.now() }] }));

  const send = async (q) => {
    const msg = (q ?? text).trim();
    if (!msg || busy) return;
    setText(""); setBusy(true);
    add({ from: "me", text: msg });
    try {
      const r = await post("/api/chat", { member_id: ui.memberId, text: msg });
      add({ from: "bot", text: r.reply, actions: r.actions || [] });
      setEngine(r.engine || "rules");
      setSuggest(r.engine === "adk" ? START_ADK : r.suggestions);
    } catch (e) {
      add({ from: "bot", text: "Sorry, I couldn't reach the server. " + e.message });
    } finally { setBusy(false); }
  };

  return (
    <div className="chat">
      <div className="chead">
        <span className="avatar brand lg">W</span>
        <div><b>Waypoint concierge</b><small><i className="dot on" /> {engine === "adk" ? "Gemini · Google ADK agent" : "watching your trips"}</small></div>
      </div>

      <div className="msgs" aria-live="polite">
        {thread.map((m, i) =>
          m.kind === "decision" ? <DecisionBubble key={"d" + m.d.id} d={m.d} /> : (
            <div key={i} className={"bubble " + m.from}>
              {m.text.split("\n").map((l, j) => <p key={j}>{l}</p>)}
              {(m.actions || []).map((a, k) => <ActionCard key={k} a={a} />)}
            </div>
          )
        )}
        {busy && <div className="bubble bot typing" aria-label="Waypoint is typing"><i /><i /><i /></div>}
        <div ref={end} />
      </div>

      <div className="quick">
        {suggest.map((s) => <button key={s} className="chip2" onClick={() => send(s)}>{s}</button>)}
      </div>
      <form className="composer" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about budget, limits, bookings…" aria-label="Message" />
        <button type="submit" aria-label="Send" disabled={!text.trim() || busy}><Icon name="send" size={20} /></button>
      </form>
    </div>
  );
}

function DecisionBubble({ d }) {
  const ui = useUI();
  const st = STATUS[d.status] || { label: d.status, tone: "muted" };
  const act = (p) => post(p).catch((e) => ui.toast(e.message));
  return (
    <div className="bubble bot alert">
      <small className={"tagline " + st.tone}>{st.label}</small>
      <p>{d.notification}</p>
      {d.status === "NEEDS_APPROVAL" && (
        <div className="cta">
          <button className="btn primary sm" onClick={() => act(`/api/decisions/${d.id}/approve`)}>Approve {inr(d.chosen_amount)}</button>
          <button className="btn sm" onClick={() => act(`/api/decisions/${d.id}/decline`)}>Decline</button>
        </div>
      )}
      {d.status === "FALLBACK_OPTIONS" && (
        <div className="cta col">
          {d.options.map((o, i) => (
            <button key={i} className="opt sm" onClick={() => act(`/api/decisions/${d.id}/choose/${i}`)}>
              <span>{o.label}</span><b>{inr(o.total_cost)}</b>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** A proposal from the agent. Nothing happens until the member taps Confirm. */
function ActionCard({ a }) {
  const ui = useUI();
  const [st, setSt] = useState("idle"); // idle | busy | done | no
  const confirm = async () => {
    setSt("busy");
    try {
      if (a.type === "switch") await post(`/api/bookings/${a.booking_id}/switch`, { label: a.label });
      else await post("/api/cancel", { trip_id: a.trip_id, booking_id: a.booking_id, reason: a.reason, note: a.note || "" });
      setSt("done");
    } catch (e) { ui.toast(e.message); setSt("idle"); }
  };
  return (
    <div className={"acard " + (a.warn ? "warn" : "")}>
      <b>{a.title}</b>
      <p>{a.detail}</p>
      {a.type === "cancel" && a.items && a.items.length > 1 && (
        <ul>{a.items.map((i) => <li key={i.booking_id}><span>{i.label}</span><b>{inr(i.refund)}</b></li>)}</ul>
      )}
      {st === "done" ? <small className="tagline good">Done. I sent you the confirmation.</small>
        : st === "no" ? <small className="muted">Okay, left as it is.</small>
        : (
          <div className="cta">
            <button className={"btn sm " + (a.type === "cancel" ? "danger" : "primary")} disabled={st === "busy"} onClick={confirm}>{a.confirm}</button>
            <button className="btn sm" disabled={st === "busy"} onClick={() => setSt("no")}>Not now</button>
          </div>
        )}
    </div>
  );
}

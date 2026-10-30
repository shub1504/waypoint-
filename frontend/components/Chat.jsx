import { useEffect, useMemo, useRef, useState } from "react";
import { STATUS, inr, post } from "../api.js";
import { useUI } from "../ui.js";
import { Icon } from "./Icons.jsx";

const START = ["How much budget is left?", "What is my auto-rebook limit?", "Why did you pick that?", "Show my bookings"];

export default function Chat() {
  const ui = useUI();
  const me = ui.members.find((m) => m.id === ui.memberId);
  const [typed, setTyped] = useState({}); // per member: [{from, text, t}]
  const [suggest, setSuggest] = useState(START);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef(null);

  const thread = useMemo(() => {
    const own = typed[ui.memberId] || [];
    const decisions = ui.decisions
      .filter((d) => d.member_id === ui.memberId)
      .map((d) => ({ kind: "decision", d, t: new Date(d.created_at).getTime() }));
    const hello = { kind: "text", from: "bot", t: 0, text: `Hi ${me ? me.name.split(" ")[0] : ""}, I'm Waypoint. I'll message you here whenever something on your trip changes. You can also ask me about your budget, limits or bookings.` };
    return [hello, ...own.map((m) => ({ kind: "text", ...m })), ...decisions].sort((a, b) => a.t - b.t);
  }, [typed, ui.decisions, ui.memberId, me]);

  useEffect(() => { end.current && end.current.scrollIntoView({ block: "end" }); }, [thread.length]);

  const add = (m) => setTyped((s) => ({ ...s, [ui.memberId]: [...(s[ui.memberId] || []), { ...m, t: Date.now() }] }));

  const send = async (q) => {
    const msg = (q ?? text).trim();
    if (!msg || busy) return;
    setText(""); setBusy(true);
    add({ from: "me", text: msg });
    try {
      const r = await post("/api/chat", { member_id: ui.memberId, text: msg });
      add({ from: "bot", text: r.reply });
      setSuggest(r.suggestions);
    } catch (e) {
      add({ from: "bot", text: "Sorry, I couldn't reach the server. " + e.message });
    } finally { setBusy(false); }
  };

  return (
    <div className="chat">
      <div className="chead">
        <span className="avatar brand lg">W</span>
        <div><b>Waypoint concierge</b><small><i className="dot on" /> watching your trips</small></div>
      </div>

      <div className="msgs" aria-live="polite">
        {thread.map((m, i) =>
          m.kind === "decision" ? <DecisionBubble key={"d" + m.d.id} d={m.d} /> : (
            <div key={i} className={"bubble " + m.from}>{m.text.split("\n").map((l, j) => <p key={j}>{l}</p>)}</div>
          )
        )}
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

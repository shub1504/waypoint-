import { useEffect, useMemo, useRef, useState } from "react";
import { KIND_ICON, STATUS, ago, get, inr, post } from "../api.js";
import { useUI } from "../ui.js";
import { Icon } from "./Icons.jsx";

const START = ["How much budget is left?", "What is my auto-rebook limit?", "Why did you pick that?", "Show my bookings"];
const START_ADK = ["How much budget is left?", "Show cheaper options for my hotel", "Cancel my trip, my plans changed", "Why did you pick that?"];
const isTravel = (s) => /\b(travel|trip|journey|itinerary|train|flight|airline|hotel|stay|destination|tour|vacation|holiday|ticket|book a|plan a trip|go to|travel to)\b/i.test(s);

function getThreadId(memberId) {
  const key = "waypoint_langgraph_thread_" + memberId;
  let id = localStorage.getItem(key);
  if (!id) {
    id = globalThis.crypto?.randomUUID?.() || ("wp-" + Date.now() + "-" + Math.random().toString(36).slice(2));
    localStorage.setItem(key, id);
  }
  return id;
}

async function streamAgent(path, body, handlers) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed (${response.status})`);
  }
  if (!response.body) throw new Error("Streaming response is unavailable.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let tokenText = "";

  const dispatch = (block) => {
    let event = "message";
    const data = [];
    block.split(/\r?\n/).forEach((line) => {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trim());
    });
    if (!data.length) return;
    let payload;
    try { payload = JSON.parse(data.join("\n")); } catch { return; }

    if (event === "token") {
      tokenText += payload.content || "";
      handlers.onToken?.(tokenText);
    } else if (event === "progress") {
      handlers.onProgress?.(payload.name || payload.event || "Working...");
    } else if (event === "interrupt") {
      handlers.onInterrupt?.(payload.payload || payload);
    } else if (event === "complete") {
      handlers.onComplete?.(payload.state || {}, tokenText);
    } else if (event === "error") {
      throw new Error(payload.message || "Travel agent error");
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() || "";
    blocks.forEach(dispatch);
  }
  buffer += decoder.decode();
  if (buffer.trim()) dispatch(buffer);
}

export default function Chat() {
  const ui = useUI();
  const me = ui.members.find((m) => m.id === ui.memberId);
  const memberId = String(ui.memberId);
  const [typed, setTyped] = useState({});
  const [suggest, setSuggest] = useState(START);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [engine, setEngine] = useState("rules");
  const [interrupt, setInterrupt] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [progress, setProgress] = useState("");
  const end = useRef(null);
  const threadId = useMemo(() => getThreadId(memberId), [memberId]);

  useEffect(() => {
    get("/api/health").then((h) => {
      setEngine(h.chat || "rules");
      if (h.chat === "adk") setSuggest(START_ADK);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    let active = true;
    setInterrupt(null);
    setSelectedIds([]);
    get("/api/travel-agent/state/" + encodeURIComponent(threadId))
      .then((r) => {
        if (!active) return;
        const pending = r.interrupts?.[0];
        if (pending) setInterrupt(pending);
      })
      .catch(() => {});
    return () => { active = false; };
  }, [threadId]);

  const thread = useMemo(() => {
    const own = typed[memberId] || [];
    const decisions = ui.decisions
      .filter((d) => d.member_id === ui.memberId)
      .map((d) => ({ kind: "decision", d, t: new Date(d.created_at).getTime() }));
    const hello = {
      kind: "text", from: "bot", t: 0,
      text: `Hi ${me ? me.name.split(" ")[0] : ""}, I'm Waypoint. I'll message you here whenever something on your trip changes. You can also ask me about your budget, limits or bookings.`
    };
    return [hello, ...own.map((m) => ({ kind: "text", ...m })), ...decisions].sort((a, b) => a.t - b.t);
  }, [typed, ui.decisions, memberId, ui.memberId, me]);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [thread.length, busy, interrupt, progress]);

  const add = (m) => setTyped((s) => ({
    ...s, [memberId]: [...(s[memberId] || []), { ...m, t: Date.now() }]
  }));

  const handleGraphEvents = {
    onToken: (value) => setProgress(value ? "Generating response..." : "Working..."),
    onProgress: (value) => setProgress(value),
    onInterrupt: (payload) => {
      setInterrupt(payload);
      setSelectedIds([]);
      setProgress("");
    },
    onComplete: (state, tokens) => {
      setInterrupt(null);
      setProgress("");
      const answer = state.assistant_message || state.booking_result?.message || "";
      if (!tokens?.trim() && answer) add({ from: "bot", text: answer });
      if (state.booking_result) {
        const result = state.booking_result;
        add({
          from: "bot",
          text: `${result.status ? "Booking status: " + result.status.toUpperCase() + "\n" : ""}${result.message || ""}${result.booking_reference ? "\nReference: " + result.booking_reference : ""}`
        });
      }
    },
    onError: (message) => {
      setProgress("");
      add({ from: "bot", text: "Travel agent error: " + message });
    }
  };

  const runGraph = async (message) => {
    setEngine("langgraph");
    setProgress("Connecting to travel agent...");
    await streamAgent("/api/travel-agent/chat", { thread_id: threadId, message }, handleGraphEvents);
  };

  const resumeGraph = async (decision) => {
    if (busy) return;
    setBusy(true);
    setProgress("Processing your approval...");
    try {
      await streamAgent("/api/travel-agent/resume", { thread_id: threadId, decision }, handleGraphEvents);
    } catch (e) {
      add({ from: "bot", text: "Could not submit approval: " + e.message });
    } finally {
      setBusy(false);
      setProgress("");
    }
  };

  const send = async (q) => {
    const msg = (q ?? text).trim();
    if (!msg || busy) return;
    setText("");
    setBusy(true);
    add({ from: "me", text: msg });
    try {
      if (isTravel(msg)) {
        await runGraph(msg);
      } else {
        const r = await post("/api/chat", { member_id: ui.memberId, text: msg });
        add({ from: "bot", text: r.reply, actions: r.actions || [] });
        setEngine(r.engine || "rules");
        setSuggest(r.engine === "adk" ? START_ADK : (r.suggestions || START));
      }
    } catch (e) {
      add({ from: "bot", text: "Sorry, I couldn't reach the server. " + e.message });
    } finally {
      setBusy(false);
      setProgress("");
    }
  };

  const toggleOption = (id) => {
    setSelectedIds((old) => old.includes(id) ? old.filter((x) => x !== id) : [...old, id]);
  };

  const approveSelection = () => {
    if (!selectedIds.length) return;
    resumeGraph({
      approved_option_ids: selectedIds,
      user_message: "I selected these options: " + selectedIds.join(", ")
    });
  };

  const categories = [
    ["trains", "Train"],
    ["flights", "Flight"],
    ["hotels", "Hotel"]
  ];

  return (
    <div className="chat">
      <div className="chead">
        <span className="avatar brand lg">W</span>
        <div>
          <b>Waypoint concierge</b>
          <small><i className="dot on"/> {engine === "langgraph" ? "LangGraph travel agent" : engine === "adk" ? "Gemini · Google ADK agent" : "watching your trips"}</small>
        </div>
      </div>

      <div className="msgs" aria-live="polite">
        {thread.map((m, i) =>
          m.kind === "decision" ? <DecisionBubble key={"d" + m.d.id} d={m.d} /> : (
            <div key={i} className={"bubble " + m.from}>
              {m.from === "bot" && <span className="bic">W</span>}
              <div className="bbody">
                <div className="bhead">
                  <b>{m.from === "bot" ? "Waypoint" : "You"}</b>
                  {m.t > 0 && <small>{ago(new Date(m.t).toISOString())}</small>}
                </div>
                {(m.text || "").split("\n").map((l, j) => <p key={j}>{l}</p>)}
                {(m.actions || []).map((a, k) => <ActionCard key={k} a={a} />)}
              </div>
            </div>
          )
        )}

        {interrupt?.type === "selection_approval" && (
          <div className="bubble bot">
            <span className="bic">W</span>
            <div className="bbody">
              <div className="bhead"><b>Choose your travel options</b></div>
              <p>{interrupt.message}</p>
              {categories.map(([key, label]) => {
                const options = interrupt.recommendations?.[key] || [];
                if (!options.length) return null;
                return (
                  <div key={key} style={{ marginTop: 12 }}>
                    <b>{label}s</b>
                    {options.map((o) => (
                      <label key={o.option_id} className="opt sm" style={{ display: "flex", gap: 10, alignItems: "flex-start", marginTop: 8, padding: 10, cursor: "pointer" }}>
                        <input type="checkbox" checked={selectedIds.includes(o.option_id)} onChange={() => toggleOption(o.option_id)} />
                        <span style={{ flex: 1 }}>
                          <b>{o.title}</b>
                          <small style={{ display: "block" }}>{o.provider} · {o.departure || ""} {o.arrival ? "→ " + o.arrival : ""}</small>
                          <small style={{ display: "block" }}>{o.duration || ""} · Fit {o.fit_score ?? "–"}%</small>
                        </span>
                        <b>{inr(o.price_inr)}</b>
                      </label>
                    ))}
                  </div>
                );
              })}
              <div className="cta">
                <button className="btn primary sm" disabled={!selectedIds.length || busy} onClick={approveSelection}>
                  Continue with {selectedIds.length} selected
                </button>
              </div>
            </div>
          </div>
        )}

        {interrupt?.type === "payment_approval" && (
          <div className="bubble bot alert">
            <span className="bic">W</span>
            <div className="bbody">
              <div className="bhead"><b>Final payment approval</b></div>
              <p>{interrupt.message}</p>
              {(interrupt.selected_options || []).map((o) => (
                <div key={o.option_id} className="opt sm" style={{ marginTop: 8, padding: 10 }}>
                  <b>{o.title}</b><span> · {o.provider}</span>
                  <b style={{ float: "right" }}>{inr(o.price_inr)}</b>
                </div>
              ))}
              <p><b>Total: {inr(interrupt.total_price_inr)}</b></p>
              <small>Nothing proceeds unless you explicitly approve.</small>
              <div className="cta">
                <button className="btn primary sm" disabled={busy} onClick={() => resumeGraph({
                  approved: true,
                  confirmation_text: `APPROVE ${Number(interrupt.total_price_inr || 0).toFixed(2)} INR`
                })}>Approve exact amount</button>
                <button className="btn sm" disabled={busy} onClick={() => resumeGraph({
                  approved: false,
                  confirmation_text: "User rejected payment/booking."
                })}>Reject</button>
              </div>
            </div>
          </div>
        )}

        {busy && (
          <div className="bubble bot typing" aria-label="Waypoint is typing">
            <img src="/favicon.svg" alt="Waypoint" className="typing-logo"/>
            <span>{progress || "Waypoint is thinking..."}</span>
          </div>
        )}
        <div ref={end} />
      </div>

      <div className="quick">
        {suggest.map((s) => <button key={s} className="chip2" onClick={() => send(s)}>{s}</button>)}
      </div>
      <form className="composer" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about trips, budget, limits, bookings..." aria-label="Message" />
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
      <span className="bic"><Icon name={KIND_ICON[d.kind] || "plane"} size={18} /></span>
      <div className="bbody">
        <div className="bhead"><b className={"tl " + st.tone}>{st.label}</b><small>{ago(d.created_at)}</small></div>
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
    </div>
  );
}

function ActionCard({ a }) {
  const ui = useUI();
  const [st, setSt] = useState("idle");
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

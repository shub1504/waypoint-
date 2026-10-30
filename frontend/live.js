import { useCallback, useEffect, useRef, useState } from "react";
import { get } from "./api.js";

/** One WebSocket, plus the data every tab reads. Reconnects by itself. */
export function useLive(onNewDecision) {
  const [decisions, setDecisions] = useState([]);
  const [events, setEvents] = useState([]);
  const [trips, setTrips] = useState([]);
  const [members, setMembers] = useState([]);
  const [connected, setConnected] = useState(false);
  const known = useRef(new Set());
  const retry = useRef(0);
  const cb = useRef(onNewDecision);
  cb.current = onNewDecision;

  const loadTrips = useCallback(() => get("/api/trips").then(setTrips).catch(() => {}), []);
  const loadDecisions = useCallback(
    () =>
      get("/api/decisions")
        .then((d) => { known.current = new Set(d.map((x) => x.id)); setDecisions(d); })
        .catch(() => {}),
    []
  );
  const loadMembers = useCallback(() => get("/api/members").then(setMembers).catch(() => {}), []);

  useEffect(() => {
    loadTrips(); loadDecisions(); loadMembers();
    let ws, timer, closed = false;
    const open = () => {
      ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
      ws.onopen = () => { setConnected(true); retry.current = 0; };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) timer = setTimeout(open, Math.min(5000, 500 * 2 ** retry.current++));
      };
      ws.onmessage = (m) => {
        const msg = JSON.parse(m.data);
        if (msg.type === "event") setEvents((e) => [{ ...msg.data, seen: Date.now() }, ...e].slice(0, 8));
        if (msg.type === "decision") {
          const d = msg.data;
          const isNew = !known.current.has(d.id);
          known.current.add(d.id);
          setDecisions((list) => [d, ...list.filter((x) => x.id !== d.id)].sort((a, b) => b.id - a.id));
          if (isNew) cb.current && cb.current(d);
        }
        if (msg.type === "trips_changed") loadTrips();
        if (msg.type === "member_changed") setMembers((ms) => ms.map((x) => (x.id === msg.data.id ? msg.data : x)));
        if (msg.type === "reset") {
          known.current = new Set();
          setDecisions([]); setEvents([]); loadTrips(); loadMembers();
        }
      };
    };
    open();
    return () => { closed = true; clearTimeout(timer); ws && ws.close(); };
  }, [loadTrips, loadDecisions, loadMembers]);

  return { decisions, events, trips, members, setMembers, connected, reloadTrips: loadTrips };
}

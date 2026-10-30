import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { inr } from "./api.js";
import { useLive } from "./live.js";
import { useMedia } from "./useMedia.js";
import { UI } from "./ui.js";
import { Icon } from "./components/Icons.jsx";
import Home from "./components/Home.jsx";
import Explore from "./components/Explore.jsx";
import Chat from "./components/Chat.jsx";
import Profile from "./components/Profile.jsx";
import DemoPanel from "./components/DemoPanel.jsx";
import Avatar from "./components/Avatar.jsx";
import Logo from "./components/Logo.jsx";
import AddAccount from "./components/AddAccount.jsx";
import { TripSheet } from "./components/TripCard.jsx";

const TABS = [
  { id: "home", label: "Home", icon: "home" },
  { id: "explore", label: "Explore", icon: "compass" },
  { id: "chat", label: "Chat", icon: "chat" },
  { id: "profile", label: "Profile", icon: "user" },
];

function loadMember() {
  try { return localStorage.getItem("wp_member") || "M001"; } catch { return "M001"; }
}

export default function App() {
  const desktop = useMedia("(min-width: 900px)"); // laptop layout: sidebar + centred feed
  const rail = useMedia("(min-width: 1180px)");   // wide laptop: right column + labelled sidebar
  const [tab, setTab] = useState("home");
  const [memberId, setMemberIdRaw] = useState(loadMember);
  const [sheet, setSheet] = useState(null);
  const [toastMsg, setToastMsg] = useState(null);
  const [unread, setUnread] = useState({ home: 0, chat: 0 });
  const [exploreTarget, setExploreTarget] = useState(null);
  const screen = useRef(null);

  const setMemberId = useCallback((id) => {
    setMemberIdRaw(id);
    try { localStorage.setItem("wp_member", id); } catch { /* private mode: fine */ }
  }, []);

  const toast = useCallback((text, action) => setToastMsg({ text, action, n: Date.now() }), []);
  useEffect(() => {
    if (!toastMsg) return;
    const t = setTimeout(() => setToastMsg(null), toastMsg.action ? 7000 : 4000);
    return () => clearTimeout(t);
  }, [toastMsg]);

  // refs so the WebSocket callback always sees the current tab/member without reconnecting
  const live = useRef({});
  const onNewDecision = useCallback((d) => {
    const { tab, memberId, members } = live.current;
    if (d.member_id !== memberId) {
      const m = (members || []).find((x) => x.id === d.member_id);
      toast(`${m ? m.name.split(" ")[0] : d.member_id} has a new alert`, { label: "View", run: () => setMemberId(d.member_id) });
      return;
    }
    toast(d.notification);
    setUnread((u) => ({ home: tab === "home" ? 0 : u.home + 1, chat: tab === "chat" ? 0 : u.chat + 1 }));
  }, [toast, setMemberId]);

  const data = useLive(onNewDecision);
  live.current = { tab, memberId, members: data.members };

  const go = useCallback((id, params) => {
    setTab(id);
    setExploreTarget(params || null);
    setUnread((u) => (id === "home" || id === "chat" ? { ...u, [id]: 0 } : u));
    if (screen.current) screen.current.scrollTop = 0;
  }, []);

  const openSheet = useCallback((title, node) => setSheet({ title, node }), []);
  const closeSheet = useCallback(() => setSheet(null), []);
  const me = data.members.find((m) => m.id === memberId);

  const openAccounts = useCallback(
    () => setSheet({
      title: "Switch account",
      node: (
        <ul className="accounts">
          {data.members.map((m) => (
            <li key={m.id}>
              <button onClick={() => { setMemberId(m.id); setSheet(null); }} aria-current={m.id === memberId}>
                <Avatar m={m} />
                <span><b>{m.name}</b><small>{m.budget_level} budget Â· {m.home_city}</small></span>
                {m.id === memberId && <Icon name="check" size={18} />}
              </button>
            </li>
          ))}
          <li>
            <button className="addrow" onClick={() => setSheet({ title: "Add account", node: <AddAccount /> })}>
              <span className="avatar">+</span><span><b>Add account</b><small>New member with a starter trip</small></span>
            </button>
          </li>
        </ul>
      ),
    }),
    [data.members, memberId, setMemberId]
  );
  const openDemo = useCallback(() => setSheet({ title: "Demo controls", node: <DemoPanel /> }), []);

  const ctx = useMemo(
    () => ({ ...data, memberId, setMemberId, openSheet, closeSheet, toast, go, exploreTarget, openDemo, openAccounts, desktop }),
    [data, memberId, setMemberId, openSheet, closeSheet, toast, go, exploreTarget, openDemo, openAccounts, desktop]
  );

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && setSheet(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const myTrips = data.trips.filter((t) => t.member.id === memberId);
  const others = data.members.filter((m) => m.id !== memberId);
return (
    <UI.Provider value={ctx}>
      <div className={"app " + (desktop ? "desk" : "mob")}>
        {desktop && (
          <aside className="side" aria-label="Main">
            <div className="brandmark"><Logo size={30} /><b>Waypoint</b></div>
            {TABS.map((t) => (
              <button key={t.id} className={"nav " + (tab === t.id ? "on" : "")} onClick={() => go(t.id)} aria-label={t.label} aria-current={tab === t.id ? "page" : undefined}>
                {t.id === "profile" && me ? <Avatar m={me} cls="xs" /> : <Icon name={t.icon} size={26} />}
                <span className="lbl">{t.label}</span>
                {unread[t.id] > 0 && <i className="badge">{unread[t.id]}</i>}
              </button>
            ))}
            <div className="grow" />
            {!rail && (
              <button className="nav" onClick={openDemo} aria-label="Demo controls"><Icon name="flask" size={26} /><span className="lbl">Demo controls</span></button>
            )}
            <button className="nav" onClick={openAccounts} aria-label="Switch account"><Icon name="swap" size={26} /><span className="lbl">Switch account</span></button>
          </aside>
        )}

        <div className="main">
          {!desktop && (
            <header className="topbar">
              <div className="brandmark"><Logo size={30} /><b>Waypoint</b></div>
              <div className="tools">
                <button className="icon flask" onClick={openDemo} aria-label="Demo controls"><Icon name="flask" size={22} /></button>
                <Avatar tag="button" m={me} cls="sm" onClick={openAccounts} aria-label={`Account: ${me ? me.name : ""}. Switch account`} />
              </div>
            </header>
          )}

          <main className={"screen" + (tab === "chat" ? " noscroll" : "")} ref={screen}>
            <div className={"col " + tab}>
              {tab === "home" && <Home />}
              {tab === "explore" && <Explore />}
              {tab === "chat" && <Chat />}
              {tab === "profile" && <Profile />}
            </div>
          </main>

          {!desktop && (
            <nav className="tabbar" aria-label="Main">
              {TABS.map((t) => (
                <button key={t.id} className={tab === t.id ? "on" : ""} onClick={() => go(t.id)} aria-label={t.label} aria-current={tab === t.id ? "page" : undefined}>
                  {t.id === "profile" && me ? <Avatar m={me} cls="xs" /> : <Icon name={t.icon} size={26} fill={false} />}
                  <small>{t.label}</small>
                  {unread[t.id] > 0 && <i className="badge">{unread[t.id]}</i>}
                </button>
              ))}
            </nav>
          )}
        </div>

        {rail && (
          <aside className="rail" aria-label="Account and demo">
            {me && (
              <div className="racct">
                <Avatar m={me} cls="lg" />
                <div><b>{me.name}</b><small>{me.email}</small></div>
                <button className="link" onClick={openAccounts}>Switch</button>
              </div>
            )}

            <h4 className="rh">Your trips</h4>
            {myTrips.map((t) => (
              <button key={t.id} className="rrow" onClick={() => openSheet(t.title, <TripSheet trip={t} />)}>
                <span className="avatar"><Icon name={t.bookings.some((b) => b.kind === "TRAIN") ? "train" : "plane"} size={20} /></span>
                <span><b>{t.title}</b><small>{inr(t.spent)} of {inr(t.envelope)}</small></span>
                <span className="go"><Icon name="arrow" size={18} /></span>
              </button>
            ))}

            {others.length > 0 && <h4 className="rh">Other travellers</h4>}
            {others.map((m) => (
              <div key={m.id} className="rrow static">
                <Avatar m={m} />
                <span><b>{m.name}</b><small>{m.budget_level} budget Â· {m.home_city}</small></span>
                <button className="link" onClick={() => setMemberId(m.id)}>Switch</button>
              </div>
            ))}

            <div className="rdemo"><DemoPanel /></div>
          </aside>
        )}

        {toastMsg && (
          <div className="toast" role="status" key={toastMsg.n}>
            <span>{toastMsg.text}</span>
            {toastMsg.action && <button onClick={() => { toastMsg.action.run(); setToastMsg(null); }}>{toastMsg.action.label}</button>}
          </div>
        )}

        {sheet && (
          <div className="overlay" onClick={closeSheet}>
            <div className="sheet" role="dialog" aria-modal="true" aria-label={sheet.title} onClick={(e) => e.stopPropagation()}>
              <div className="grab" />
              <div className="shead"><h3>{sheet.title}</h3><button className="icon" onClick={closeSheet} aria-label="Close"><Icon name="close" size={20} /></button></div>
              <div className="sbody">{sheet.node}</div>
            </div>
          </div>
        )}
      </div>
    </UI.Provider>
  );
}




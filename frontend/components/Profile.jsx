import { useEffect, useState } from "react";
import { KIND_ICON, get, initials, inr, patch, pay } from "../api.js";
import { useUI } from "../ui.js";
import { Icon } from "./Icons.jsx";
import Matrix, { pairCols, pairRows } from "./Matrix.jsx";

const MULT = { low: 1.3, medium: 1.6, high: 2.0 };
const LEVEL_FILL = { low: 34, medium: 67, high: 100 };
const LEVELS = {
  low: "Tighter limits: prepaid rebookings up to 1.3× the original price.",
  medium: "Balanced: prepaid rebookings up to 1.6× the original price.",
  high: "Flexible: prepaid rebookings up to 2.0× the original price.",
};
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");

const TITLES = {
  new: "New bookings", old: "Old bookings", past: "Past trips",
  budget: "Budget comfort", channel: "Alerts via", city: "Home city", perms: "Permissions", contact: "Contact",
};

export default function Profile() {
  const ui = useUI();
  const me = ui.members.find((m) => m.id === ui.memberId);
  const [page, setPage] = useState(null); // null = the "Me" menu (phone). On a laptop the right pane always shows one.
  const [data, setData] = useState({ new: [], old: [], past_stays: [] });

  useEffect(() => {
    if (!ui.memberId) return;
    get(`/api/members/${ui.memberId}/bookings`).then(setData).catch(() => {});
  }, [ui.memberId, ui.trips]);

  if (!me) return null;
  const rebooked = data.new.filter((b) => b.original).length;
  const pending = ui.decisions.filter((d) => d.member_id === me.id && ["NEEDS_APPROVAL", "FALLBACK_OPTIONS"].includes(d.status)).length;
  const cur = ui.desktop ? page || "new" : page;
  const permsOn = [me.consent_autorebook, me.consent_history].filter(Boolean).length;

  const tiles = [
    { id: "new", icon: "grid", label: "New", dot: rebooked },
    { id: "old", icon: "archive", label: "Old", dot: 0 },
    { id: "past", icon: "clock", label: "Past trips", dot: 0 },
    { id: "alerts", icon: "chat", label: "Alerts", dot: pending },
  ];
  const groups = [
    [
      { id: "budget", icon: "wallet", label: "Budget comfort", value: cap(me.budget_level) },
      { id: "channel", icon: "send", label: "Alerts via", value: me.alert_channel },
      { id: "city", icon: "pin", label: "Home city", value: me.home_city },
      { id: "perms", icon: "sliders", label: "Permissions", value: `${permsOn} of 2 on` },
    ],
    [
      { id: "contact", icon: "user", label: "Contact", value: me.phone },
      { id: "switch", icon: "swap", label: "Switch account", value: me.name.split(" ")[0] },
      { id: "help", icon: "info", label: "Ask Waypoint", value: "Chat" },
    ],
  ];

  const open = (id) => {
    if (id === "alerts" || id === "help") return ui.go("chat");
    if (id === "switch") return ui.openAccounts();
    setPage(id);
  };

  const menu = (
    <div className="pmenu">
      <div className="mehead">
        <span className="avatar sq">{initials(me.name)}</span>
        <div className="who2">
          <b>{me.name}</b>
          <div className="level" title={LEVELS[me.budget_level]}>
            <div className="lbar" role="img" aria-label={`Budget comfort ${me.budget_level}`}><i style={{ width: LEVEL_FILL[me.budget_level] + "%" }} /></div>
            <small>{cap(me.budget_level)} · {MULT[me.budget_level]}×</small>
          </div>
        </div>
        <button className="btn sm" onClick={ui.openAccounts}><Icon name="swap" size={16} /> Switch</button>
      </div>

      <div className="tiles4">
        {tiles.map((t) => (
          <button key={t.id} className={"stile " + (cur === t.id ? "on" : "")} onClick={() => open(t.id)}>
            <Icon name={t.icon} size={24} />
            <span>{t.label}</span>
            {t.dot > 0 && <i className="rdot">{t.dot}</i>}
          </button>
        ))}
      </div>

      {groups.map((g, i) => (
        <div key={i}>
          <div className="gap" />
          {g.map((r) => (
            <button key={r.id} className={"mrow " + (cur === r.id ? "on" : "")} onClick={() => open(r.id)}>
              <span className="mi"><Icon name={r.icon} size={18} /></span>
              <span className="ml">{r.label}</span>
              <span className="mv">{r.value}</span>
              <Icon name="chevron" size={18} />
            </button>
          ))}
        </div>
      ))}
      <p className="sub pad foot">{rebooked > 0 ? `${rebooked} of your bookings were rebooked by Waypoint.` : "Waypoint is watching your trips."}</p>
    </div>
  );

  const detail = (
    <div className="pdetail">
      {!ui.desktop && (
        <div className="pgbar">
          <button className="icon" onClick={() => setPage(null)} aria-label="Back"><Icon name="back" size={22} /></button>
          <h3>{TITLES[cur]}</h3>
        </div>
      )}
      {ui.desktop && <h3 className="dtitle">{TITLES[cur]}</h3>}
      {cur === "new" && <Bookings items={data.new} kind="new" />}
      {cur === "old" && <Bookings items={data.old} kind="old" />}
      {cur === "past" && <Past stays={data.past_stays} />}
      {cur === "budget" && <BudgetPage me={me} />}
      {cur === "channel" && <ChannelPage me={me} />}
      {cur === "city" && <CityPage me={me} />}
      {cur === "perms" && <PermsPage me={me} />}
      {cur === "contact" && <ContactPage me={me} />}
    </div>
  );

  if (ui.desktop) return <div className="pwrap">{menu}{detail}</div>;
  return <div className="me">{cur ? detail : menu}</div>;
}

function Bookings({ items, kind }) {
  const ui = useUI();
  if (items.length === 0)
    return <div className="empty"><p>{kind === "new" ? "No active bookings." : "Nothing has been replaced yet. When Waypoint or you swap a booking, the old one is kept here."}</p></div>;

  const compare = (b) => {
    const orig = kind === "new" ? b.original : b;
    const cur = kind === "new" ? b : b.replaced_by;
    if (!orig || !cur) return;
    ui.openSheet("Original vs now", (
      <div>
        {b.decision?.reasoning && <p className="sub">{b.decision.reasoning}</p>}
        <Matrix cols={pairCols(orig, cur, b.decision)} rows={pairRows(cur.kind === "HOTEL" ? "HOTEL" : "OTHER")} />
      </div>
    ));
  };

  return (
    <ul className="bcards">
      {items.map((b) => {
        const canCompare = kind === "new" ? !!b.original : !!b.replaced_by;
        return (
          <li key={b.id} className={"bcard " + (kind === "old" ? "old" : "")}>
            <span className="bicon"><Icon name={KIND_ICON[b.kind] || "plane"} size={22} /></span>
            <div className="binfo">
              <b>{b.label}</b>
              <small>{b.trip_title} · {pay(b.payment_type)}</small>
              {kind === "old" && b.replaced_by && <small>Replaced by {b.replaced_by.label} ({inr(b.replaced_by.amount)})</small>}
              {kind === "new" && b.original && <small className="up">Rebooked from {b.original.label} ({inr(b.original.amount)})</small>}
              {b.decision && <small>Decided by {b.decision.by}{b.decision.latency_ms ? ` in ${b.decision.latency_ms} ms` : ""}</small>}
            </div>
            <div className="bright">
              <b>{inr(b.amount)}</b>
              {canCompare && <button className="link" onClick={() => compare(b)}><Icon name="table" size={14} /> Compare</button>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function Past({ stays }) {
  if (stays.length === 0) return <div className="empty"><p>No past trips yet.</p></div>;
  return (
    <>
      <p className="sub pad">Stays Waypoint learns from. This is how it knows where you like to stay.</p>
      <div className="pgrid">
        {stays.map((s) => (
          <div key={s.id} className="ptile">
            <Icon name="bed" size={20} />
            <b>{s.purpose_place}</b>
            <small>{s.area} · {s.distance_km} km</small>
            <small>{inr(s.price_per_night)}/night</small>
            <small className="muted">{s.stayed_on}</small>
          </div>
        ))}
      </div>
    </>
  );
}

function Seg({ value, options, onChange, label }) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o} role="radio" aria-checked={value === o} className={value === o ? "on" : ""} onClick={() => onChange(o)}>{o}</button>
      ))}
    </div>
  );
}

function Toggle({ on, onChange, title, hint }) {
  return (
    <div className="toggle">
      <div><b>{title}</b><small>{hint}</small></div>
      <button role="switch" aria-checked={on} aria-label={title} className={"sw " + (on ? "on" : "")} onClick={() => onChange(!on)}><i /></button>
    </div>
  );
}

function useSave(me) {
  const ui = useUI();
  return (body) =>
    patch(`/api/members/${me.id}`, body)
      .then((m) => { ui.setMembers((ms) => ms.map((x) => (x.id === m.id ? m : x))); ui.toast("Saved"); })
      .catch((e) => ui.toast(e.message));
}

function BudgetPage({ me }) {
  const save = useSave(me);
  return (
    <div className="prefs">
      <Seg label="Budget comfort" value={me.budget_level} options={["low", "medium", "high"]} onChange={(v) => save({ budget_level: v })} />
      <p className="sub">{LEVELS[me.budget_level]} Pay-after items like hotels get up to 2.5×.</p>
    </div>
  );
}

function ChannelPage({ me }) {
  const save = useSave(me);
  return (
    <div className="prefs">
      <Seg label="Alert channel" value={me.alert_channel} options={["Push", "SMS", "Email"]} onChange={(v) => save({ alert_channel: v })} />
      <p className="sub">Where Waypoint tells you what it changed on your trip.</p>
    </div>
  );
}

function CityPage({ me }) {
  const save = useSave(me);
  const [city, setCity] = useState(me.home_city);
  useEffect(() => setCity(me.home_city), [me.id, me.home_city]);
  return (
    <div className="prefs">
      <input className="text" value={city} onChange={(e) => setCity(e.target.value)}
        onBlur={() => city !== me.home_city && city.trim() && save({ home_city: city.trim() })} aria-label="Home city" />
      <p className="sub">Helps estimate how close a stay is to where you are going.</p>
    </div>
  );
}

function PermsPage({ me }) {
  const save = useSave(me);
  return (
    <div className="prefs">
      <Toggle on={me.consent_autorebook} onChange={(v) => save({ consent_autorebook: v })}
        title="Auto-rebook within my limit" hint="Off means Waypoint asks before booking anything prepaid." />
      <Toggle on={me.consent_history} onChange={(v) => save({ consent_history: v })}
        title="Learn from my past bookings" hint="Used to pick hotels near where you usually stay." />
    </div>
  );
}

function ContactPage({ me }) {
  return (
    <div className="prefs">
      <dl className="facts"><dt>Name</dt><dd>{me.name}</dd><dt>Email</dt><dd>{me.email}</dd><dt>Phone</dt><dd>{me.phone}</dd></dl>
    </div>
  );
}

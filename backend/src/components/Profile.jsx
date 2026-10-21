import { useEffect, useState } from "react";
import { KIND_ICON, get, initials, inr, patch, pay } from "../api.js";
import { useUI } from "../ui.js";
import { Icon } from "./Icons.jsx";
import Matrix, { pairCols, pairRows } from "./Matrix.jsx";
import NewTrip from "./NewTrip.jsx";
import CancelSheet from "./CancelSheet.jsx";
import Avatar from "./Avatar.jsx";
import { GRADS, fileToAvatar, setColour, setPhoto, useAvatarLook } from "../avatar.js";

const MULT = { low: 1.3, medium: 1.6, high: 2.0 };
const LEVEL_FILL = { low: 34, medium: 67, high: 100 };
const LEVELS = {
  low: "Tighter limits: prepaid rebookings up to 1.3× the original price.",
  medium: "Balanced: prepaid rebookings up to 1.6× the original price.",
  high: "Flexible: prepaid rebookings up to 2.0× the original price.",
};
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");

const TITLES = {
  newtrip: "New trip", trips: "My trips",
  new: "New bookings", old: "Old bookings", past: "Past trips",
  edit: "Edit profile", budget: "Budget comfort", channel: "Alerts via", perms: "Permissions",
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
    { id: "new", icon: "grid", label: "New", dot: rebooked, tint: "#006fcf" },
    { id: "old", icon: "archive", label: "Old", dot: 0, tint: "#8f5600" },
    { id: "past", icon: "clock", label: "Past trips", dot: 0, tint: "#0a7a45" },
    { id: "alerts", icon: "chat", label: "Alerts", dot: pending, tint: "#b3261e" },
  ];
  const myTrips = ui.trips.filter((t) => t.member.id === me.id);
  const groups = [
    [
      { id: "newtrip", icon: "plus", label: "New trip", value: "Add details", tint: "#006fcf" },
      { id: "trips", icon: "pin", label: "My trips", value: String(myTrips.length), tint: "#00a88f" },
    ],
    [
      { id: "edit", icon: "user", label: "Edit profile", value: me.name.split(" ")[0], tint: "#006fcf" },
      { id: "budget", icon: "wallet", label: "Budget comfort", value: cap(me.budget_level), tint: "#0a7a45" },
      { id: "channel", icon: "send", label: "Alerts via", value: me.alert_channel, tint: "#7c3aed" },
      { id: "perms", icon: "sliders", label: "Permissions", value: `${permsOn} of 2 on`, tint: "#8f5600" },
    ],
    [
      { id: "switch", icon: "swap", label: "Switch account", value: me.name.split(" ")[0], tint: "#0ea5e9" },
      { id: "help", icon: "info", label: "Ask Waypoint", value: "Chat", tint: "#00a88f" },
    ],
  ];

  const open = (id) => {
    if (id === "alerts" || id === "help") return ui.go("chat");
    if (id === "switch") return ui.openAccounts();
    setPage(id);
  };

  const menu = (
    <div className="pmenu">
      <button className="mehead" onClick={() => open("edit")} aria-label="Edit profile">
        <Avatar m={me} cls="sq" />
        <span className="who2">
          <b>{me.name}</b>
          <span className="level" title={LEVELS[me.budget_level]}>
            <span className="lbar" role="img" aria-label={`Budget comfort ${me.budget_level}`}><i style={{ width: LEVEL_FILL[me.budget_level] + "%" }} /></span>
            <small>{cap(me.budget_level)} · {MULT[me.budget_level]}×</small>
          </span>
        </span>
        <Icon name="chevron" size={20} />
      </button>

      <div className="tiles4">
        {tiles.map((t) => (
          <button key={t.id} className={"stile " + (cur === t.id ? "on" : "")} onClick={() => open(t.id)}>
            <span className="ticon" style={{ background: t.tint + "1f", color: t.tint }}><Icon name={t.icon} size={24} /></span>
            <span>{t.label}</span>
            {t.dot > 0 && <i className="rdot">{t.dot}</i>}
          </button>
        ))}
      </div>

      {groups.map((g, i) => (
        <div key={i} className="mgroup">
          {g.map((r) => (
            <button key={r.id} className={"mrow " + (cur === r.id ? "on" : "")} onClick={() => open(r.id)}>
              <span className="mi" style={{ background: r.tint + "1f", color: r.tint }}><Icon name={r.icon} size={18} /></span>
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
      {cur === "newtrip" && <NewTrip onDone={() => setPage("trips")} />}
      {cur === "trips" && <MyTrips trips={myTrips} />}
      {cur === "edit" && <EditProfile me={me} />}
      {cur === "budget" && <BudgetPage me={me} />}
      {cur === "channel" && <ChannelPage me={me} />}
      {cur === "perms" && <PermsPage me={me} />}
    </div>
  );

  if (ui.desktop) return <div className="pwrap">{menu}{detail}</div>;
  return <div className="me">{cur ? detail : menu}</div>;
}

function Bookings({ items, kind }) {
  const ui = useUI();
  if (items.length === 0)
    return <div className="empty"><p>{kind === "new" ? "No active bookings." : "Nothing has been replaced yet. When Waypoint or you swap a booking, the old one is kept here."}</p></div>;

  const cancelBooking = (b) => {
    const trip = ui.trips.find((t) => t.id === b.trip_id);
    if (trip) ui.openSheet("Cancel booking", <CancelSheet trip={trip} booking={b} />);
  };

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
              {kind === "old" && b.cancelled && <small className="up">Cancelled: {b.cancelled.reason}{b.cancelled.note ? ` (${b.cancelled.note})` : ""} · refund {inr(b.cancelled.refund)}</small>}
              {kind === "new" && b.original && <small className="up">Rebooked from {b.original.label} ({inr(b.original.amount)})</small>}
              {kind === "new" && b.auto_limit != null && <small className="lim">Auto limit {inr(b.auto_limit)} · {inr(b.baseline_amount)} × {b.multiplier}{b.pool_credit > 0 ? ` + ${inr(b.pool_credit)} pool` : ""}</small>}
              {b.decision && <small>Decided by {b.decision.by}{b.decision.latency_ms ? ` in ${b.decision.latency_ms} ms` : ""}</small>}
            </div>
            <div className="bright">
              <b>{inr(b.amount)}</b>
              {canCompare && <button className="link" onClick={() => compare(b)}><Icon name="table" size={14} /> Compare</button>}
              {kind === "new" && <button className="link warnlink" onClick={() => cancelBooking(b)}><Icon name="close" size={14} /> Cancel</button>}
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

/** One row of the Edit profile list: label left, value right, chevron (or a switch). */
function Row({ label, value, onClick, right, plain }) {
  const body = (
    <>
      <span className="ml">{label}</span>
      <span className="mv">{value}</span>
      {right || (plain ? <span className="chev-sp" /> : <Icon name="chevron" size={18} />)}
    </>
  );
  return plain
    ? <div className="mrow plain">{body}</div>
    : <button className="mrow" onClick={onClick}>{body}</button>;
}

function TextSheet({ field, label, hint, type = "text" }) {
  const ui = useUI();
  const me = ui.members.find((m) => m.id === ui.memberId);
  const save = useSave(me);
  const [v, setV] = useState(me[field] || "");
  const go = () => v.trim() && save({ [field]: v.trim() }).then(() => ui.closeSheet());
  return (
    <form onSubmit={(e) => { e.preventDefault(); go(); }}>
      <input className="text" type={type} value={v} onChange={(e) => setV(e.target.value)} aria-label={label} autoFocus />
      {hint && <p className="sub">{hint}</p>}
      <button className="btn primary" type="submit" disabled={!v.trim()}>Save</button>
    </form>
  );
}

function ChoiceSheet({ field, label, options }) {
  const ui = useUI();
  const me = ui.members.find((m) => m.id === ui.memberId);
  const save = useSave(me);
  return <div className="prefs"><Seg label={label} value={me[field]} options={options} onChange={(v) => save({ [field]: v })} /></div>;
}

function AvatarSheet({ m }) {
  const ui = useUI();
  const look = useAvatarLook(m.id);
  const onFile = async (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!f) return;
    try { setPhoto(m.id, await fileToAvatar(f)); ui.toast("Photo updated"); } catch (err) { ui.toast(err.message); }
  };
  return (
    <div className="avpick">
      <div className="avnow"><Avatar m={m} cls="xl" /></div>
      <div className="avbtns">
        <label className="btn primary">
          Upload a photo
          <input type="file" accept="image/*" onChange={onFile} hidden />
        </label>
        {look.photo && <button className="btn" onClick={() => setPhoto(m.id, null)}>Remove photo</button>}
      </div>
      <p className="sub">Or pick a colour for your initials. Your photo stays on this device.</p>
      <div className="avgrid">
        {GRADS.map((g, i) => (
          <button key={i} className={!look.photo && look.colour === i ? "on" : ""} aria-label={`Colour ${i + 1}`}
            onClick={() => { setPhoto(m.id, null); setColour(m.id, i); }}>
            <span className="avatar sq" style={{ background: g, color: "#fff", border: 0 }}>{initials(m.name)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function ContactCard({ me }) {
  return (
    <div className="ccard">
      <Avatar m={me} cls="xl" />
      <b>{me.name}</b>
      <span>{me.email}</span>
      <span>{me.phone}</span>
      <small>Shared with airlines and hotels only when a booking needs it.</small>
    </div>
  );
}

function EditProfile({ me }) {
  const ui = useUI();
  const save = useSave(me);
  const sheet = (title, node) => ui.openSheet(title, node);
  return (
    <div className="elist">
      <div className="mgroup">
        <Row label="Avatar" value={<Avatar m={me} cls="sm" />}
          onClick={() => sheet("Profile picture", <AvatarSheet m={me} />)} />
        <Row label="Name" value={me.name} onClick={() => sheet("Name", <TextSheet field="name" label="Name" />)} />
        <Row label="Member ID" value={me.id} plain />
        <Row label="Contact card" value={<Icon name="grid" size={20} />} onClick={() => sheet("Contact card", <ContactCard me={me} />)} />
      </div>
      <div className="mgroup">
        <Row label="Email" value={me.email} onClick={() => sheet("Email", <TextSheet field="email" label="Email" type="email" />)} />
        <Row label="Phone" value={me.phone} onClick={() => sheet("Phone", <TextSheet field="phone" label="Phone" type="tel" />)} />
        <Row label="Home city" value={me.home_city} onClick={() => sheet("Home city", <TextSheet field="home_city" label="Home city" hint="Helps estimate how close a stay is to where you are going." />)} />
      </div>
      <div className="mgroup">
        <Row label="Budget comfort" value={cap(me.budget_level)} onClick={() => sheet("Budget comfort", <ChoiceSheet field="budget_level" label="Budget comfort" options={["low", "medium", "high"]} />)} />
        <Row label="Alerts via" value={me.alert_channel} onClick={() => sheet("Alerts via", <ChoiceSheet field="alert_channel" label="Alert channel" options={["Push", "SMS", "Email"]} />)} />
        <Row label="Auto-rebook" plain value="" right={<button role="switch" aria-checked={me.consent_autorebook} aria-label="Auto-rebook" className={"sw " + (me.consent_autorebook ? "on" : "")} onClick={() => save({ consent_autorebook: !me.consent_autorebook })}><i /></button>} />
        <Row label="Learn from history" plain value="" right={<button role="switch" aria-checked={me.consent_history} aria-label="Learn from history" className={"sw " + (me.consent_history ? "on" : "")} onClick={() => save({ consent_history: !me.consent_history })}><i /></button>} />
      </div>
    </div>
  );
}

const BSTATUS = { ACTIVE: "Active", REBOOKED: "Replaced", CANCELLED: "Cancelled" };

function MyTrips({ trips }) {
  const ui = useUI();
  if (trips.length === 0)
    return <div className="empty"><h3>No trips yet</h3><p>Add a trip you have booked and Waypoint will look after it.</p>
      <button className="btn primary" onClick={() => ui.go("profile")}>Use "New trip" in the menu</button></div>;
  return (
    <ul className="tcards">
      {trips.map((t) => {
        const active = t.bookings.filter((b) => b.status === "ACTIVE");
        const done = active.length === 0;
        return (
          <li key={t.id} className={"tcard " + (done ? "done" : "")}>
            <div className="thead"><b>{t.title}</b><span className={"chip " + (done ? "muted" : "good")}>{done ? "Cancelled" : "Active"}</span></div>
            <small>{t.purpose} · committed {inr(t.spent)} of {inr(t.envelope)}</small>
            <ul className="blist">
              {t.bookings.map((b) => (
                <li key={b.id} className={b.status !== "ACTIVE" ? "old" : ""}>
                  <Icon name={KIND_ICON[b.kind] || "plane"} size={18} />
                  <span>{b.label}<small>{BSTATUS[b.status] || b.status}</small>{b.status === "ACTIVE" && b.auto_limit != null && <small className="lim">Auto limit {inr(b.auto_limit)} ({inr(b.baseline_amount)} × {b.multiplier})</small>}</span>
                  {b.status === "ACTIVE"
                    ? <span className="bact"><b>{inr(b.amount)}</b><button className="link warnlink" onClick={() => ui.openSheet("Cancel booking", <CancelSheet trip={t} booking={b} />)}>Cancel</button></span>
                    : <b>{inr(b.amount)}</b>}
                </li>
              ))}
            </ul>
            {!done && <button className="btn warnoutline" onClick={() => ui.openSheet("Cancel trip", <CancelSheet trip={t} />)}>Cancel whole trip</button>}
          </li>
        );
      })}
    </ul>
  );
}

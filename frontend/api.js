export const inr = (n) => (n == null ? "–" : "₹" + Math.round(n).toLocaleString("en-IN"));

export async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw new Error(e.detail || r.statusText);
  }
  return r.json();
}
export const get = (p) => api(p);
export const post = (p, body) => api(p, { method: "POST", body: body ? JSON.stringify(body) : undefined });
export const patch = (p, body) => api(p, { method: "PATCH", body: JSON.stringify(body) });

export function ago(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 10) return "just now";
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export const STATUS = {
  AUTO_BOOKED: { label: "Auto-rebooked", tone: "good" },
  NEEDS_APPROVAL: { label: "Needs approval", tone: "warn" },
  FALLBACK_OPTIONS: { label: "Choose one", tone: "warn" },
  USER_APPROVED: { label: "You approved", tone: "good" },
  USER_CHOSE: { label: "You chose", tone: "good" },
  DECLINED: { label: "Declined", tone: "muted" },
};

export const EVENT_LABEL = {
  FLIGHT_CANCELLED: "Flight cancelled",
  MISSED_CONNECTION: "Missed connection",
  TRAIN_CANCELLED: "Train cancelled",
  HOTEL_OVERBOOKED: "Hotel overbooked",
  MANUAL_SWITCH: "You switched",
};

export const KIND_ICON = { FLIGHT: "plane", HOTEL: "bed", TRAIN: "train", BUS: "bus" };
export const initials = (name = "") => name.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
export const pay = (t) => (t === "PREPAID" ? "Prepaid" : "Pay at checkout");
export const signed = (n) => (n === 0 ? "same" : (n > 0 ? "+" : "−") + inr(Math.abs(n)));

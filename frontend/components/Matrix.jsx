import { inr, pay, signed } from "../api.js";

/** Side-by-side comparison. Best value in each row is highlighted. */
export default function Matrix({ cols, rows }) {
  return (
    <div className="matrix-wrap">
      <table className="matrix">
        <thead>
          <tr>
            <th />
            {cols.map((c) => (
              <th key={c.key} className={c.highlight ? "hl" : ""}>
                <div className="mt">{c.title}</div>
                {c.sub && <small>{c.sub}</small>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const nums = cols.map((c) => (r.num ? r.num(c.data) : null));
            let best = -1;
            const valid = nums.filter((n) => n != null && !Number.isNaN(n));
            if (r.best && cols.length > 1 && valid.length > 1 && new Set(valid).size > 1) {
              const target = r.best === "min" ? Math.min(...valid) : Math.max(...valid);
              best = nums.indexOf(target);
            }
            return (
              <tr key={r.label}>
                <th scope="row">{r.label}</th>
                {cols.map((c, i) => (
                  <td key={c.key} className={i === best ? "best" : ""}>{r.get(c.data)}</td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const shortLabel = (l = "") => l.replace(/\s*\(\+ cab.*\)/, "").replace(/^Switch to bus: /, "Bus: ").replace(/^Depart from /, "From ");

/** Columns for comparing several options for one booking. */
export function optionCols(options, chosenLabel) {
  return options.map((o) => ({
    key: o.label,
    title: shortLabel(o.label),
    sub: o.via || null,
    highlight: o.label === chosenLabel,
    data: { ...o, reason: o.reason ?? o.note },
  }));
}

export function optionRows(kind, base) {
  const rows = [
    { label: "Price", get: (o) => inr(o.total_cost), num: (o) => o.total_cost, best: "min" },
    { label: "vs original", get: (o) => signed(o.total_cost - base), num: (o) => o.total_cost - base, best: "min" },
  ];
  if (kind === "HOTEL") {
    rows.push(
      { label: "Area", get: (o) => o.area ?? "–" },
      { label: "Distance", get: (o) => (o.distance_km != null ? `${o.distance_km} km` : "–"), num: (o) => o.distance_km, best: "min" },
      { label: "Relevance", get: (o) => (o.relevance != null ? o.relevance.toFixed(2) : "–"), num: (o) => o.relevance, best: "max" },
    );
  } else {
    rows.push(
      { label: "Leaves in", get: (o) => (o.depart_in_h != null ? `${Math.round(o.depart_in_h)}h` : "–"), num: (o) => o.depart_in_h, best: "min" },
      { label: "Journey", get: (o) => (o.duration_h != null ? `${o.duration_h}h` : "–"), num: (o) => o.duration_h, best: "min" },
    );
  }
  rows.push(
    { label: "Within your limit", get: (o) => <span className={o.allowed ? "yes" : "no"} title={o.reason}>{o.allowed ? "✓ Yes" : "✕ No"}</span> },
    { label: "Match score", get: (o) => (o.score != null ? o.score.toFixed(2) : "–"), num: (o) => o.score, best: "max" },
  );
  return rows;
}

/** Original booking vs what it was replaced with. */
export function pairCols(original, current, decision) {
  const base = original.baseline_amount ?? original.amount;
  const mk = (b, title, extra = {}) => ({
    key: title, title, sub: b.label, highlight: title !== "Original",
    data: { ...b, base, ...extra },
  });
  return [
    mk(original, "Original", { decided_by: "—", latency_ms: null }),
    mk(current, "Now", { decided_by: decision?.by ?? "—", latency_ms: decision?.latency_ms ?? null }),
  ];
}

export function pairRows(kind) {
  const rows = [
    { label: "Cost", get: (b) => inr(b.amount), num: (b) => b.amount, best: "min" },
    { label: "Change", get: (b) => (b.decided_by === "—" ? "—" : signed(b.amount - b.base)) },
    { label: "Payment", get: (b) => pay(b.payment_type) },
  ];
  if (kind === "HOTEL") {
    rows.push(
      { label: "Area", get: (b) => b.area ?? "–" },
      { label: "Distance", get: (b) => (b.distance_km != null ? `${b.distance_km} km` : "–"), num: (b) => b.distance_km, best: "min" },
      { label: "Nights", get: (b) => b.nights ?? "–" },
    );
  } else {
    rows.push({ label: "Route", get: (b) => (b.origin && b.destination ? `${b.origin} → ${b.destination}` : "–") });
  }
  rows.push(
    { label: "Decided by", get: (b) => b.decided_by },
    { label: "Decided in", get: (b) => (b.latency_ms != null ? (b.latency_ms ? `${b.latency_ms} ms` : "instant") : "—") },
  );
  return rows;
}

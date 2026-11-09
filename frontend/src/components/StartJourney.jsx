import { useEffect, useState } from "react";
import { get, inr, post } from "../api.js";
import { useUI } from "../ui.js";

/**
 * Start a journey: search simulated trains by station, date and budget,
 * review classes and recommendations, and book with saved PayPal.
 */
export default function StartJourney({ onDone }) {
  const ui = useUI();

  const [stations, setStations] = useState([]);
  const [stationsError, setStationsError] = useState(false);

  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [date, setDate] = useState("");
  const [budget, setBudget] = useState("");

  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState(null);
  const [selected, setSelected] = useState(null);
  const [bookingBusy, setBookingBusy] = useState(false);

  // Load available stations on mount
  useEffect(() => {
    get("/api/journey/stations")
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setStations(data);
        } else {
          setStationsError(true);
        }
      })
      .catch(() => setStationsError(true));
  }, []);

  const todayStr = () => new Date().toISOString().slice(0, 10);

  // "Fill an example" link for live demo: NDLS to UJN, 10 days out, 2000 budget
  const fillExample = () => {
    const d = new Date();
    d.setDate(d.getDate() + 10);
    const dateStr = d.toISOString().slice(0, 10);
    setFrom("NDLS");
    setTo("UJN");
    setDate(dateStr);
    setBudget("2000");
  };

  const handleSearch = async (e) => {
    if (e) e.preventDefault();
    const cleanFrom = from.trim().toUpperCase();
    const cleanTo = to.trim().toUpperCase();
    const numBudget = Number(budget);

    if (!cleanFrom || !cleanTo) {
      return ui.toast("Please specify both origin and destination stations.");
    }
    if (cleanFrom === cleanTo) {
      return ui.toast("Origin and destination stations must be different.");
    }
    if (!date) {
      return ui.toast("Please pick a journey date.");
    }
    if (date < todayStr()) {
      return ui.toast("Journey date cannot be in the past.");
    }
    if (!numBudget || numBudget <= 0) {
      return ui.toast("Please enter a budget greater than zero.");
    }

    setSearching(true);
    setSelected(null);
    try {
      const data = await get(
        `/api/journey/search?from=${encodeURIComponent(cleanFrom)}&to=${encodeURIComponent(cleanTo)}&date=${encodeURIComponent(date)}&budget=${encodeURIComponent(numBudget)}`
      );
      setResults(data);
    } catch (err) {
      ui.toast(err.message);
    } finally {
      setSearching(false);
    }
  };

  const executeBooking = async (confirmOverBudget = false) => {
    if (!selected || bookingBusy) return;
    setBookingBusy(true);

    try {
      // Step 1: verify member has saved PayPal
      const paypalStatus = await get(`/api/members/${ui.memberId}/paypal`);
      if (!paypalStatus || !paypalStatus.saved) {
        ui.toast("Save PayPal first in Profile > Payments.");
        setBookingBusy(false);
        return;
      }

      // Step 2: call book endpoint (NEVER sending a client fare or price)
      const res = await post("/api/journey/book", {
        member_id: ui.memberId,
        train_no: selected.train_no,
        cls: selected.cls,
        date: results.date,
        from: results.from,
        to: results.to,
        budget: Number(results.budget),
        confirm_over_budget: confirmOverBudget,
      });

      ui.toast("Booked and paid: " + res.label);
      if (onDone) onDone();
    } catch (err) {
      ui.toast(err.message);
    } finally {
      setBookingBusy(false);
    }
  };

  const handleBookClick = async () => {
    if (!selected || bookingBusy) return;

    // First check PayPal upfront before opening any confirmation sheet
    try {
      const paypalStatus = await get(`/api/members/${ui.memberId}/paypal`);
      if (!paypalStatus || !paypalStatus.saved) {
        ui.toast("Save PayPal first in Profile > Payments.");
        return;
      }
    } catch (err) {
      ui.toast(err.message);
      return;
    }

    // If over budget, require explicit confirmation sheet
    if (selected.fare > results.budget) {
      ui.openSheet(
        "Over budget confirmation",
        <div className="jr-confirm-sheet">
          <p className="sub">
            {"This fare is over your budget of " + inr(results.budget) + ". Book anyway?"}
          </p>
          <div className="two" style={{ marginTop: 14 }}>
            <button
              type="button"
              className="btn primary"
              disabled={bookingBusy}
              onClick={() => {
                ui.closeSheet();
                executeBooking(true);
              }}
            >
              Confirm
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => ui.closeSheet()}
            >
              Cancel
            </button>
          </div>
        </div>
      );
    } else {
      executeBooking(false);
    }
  };

  const handleSelectRec = (rec) => {
    if (!results || !results.trains) return;
    const train = results.trains.find((t) => t.train_no === rec.train_no);
    const clsInfo = train ? train.classes.find((c) => c.cls === rec.cls) : null;
    const isWL = clsInfo && (clsInfo.availability.startsWith("WL") || !clsInfo.available);
    if (isWL) {
      ui.toast("This class is on waitlist and cannot be booked.");
      return;
    }

    setSelected({
      train_no: rec.train_no,
      cls: rec.cls,
      fare: rec.fare,
      train_name: rec.train_name,
      availability: clsInfo ? clsInfo.availability : "",
      within_budget: clsInfo ? clsInfo.within_budget : rec.fare <= results.budget,
    });
  };

  return (
    <div className="nt">
      <div className="ntop">
        <p className="sub">
          Search and book simulated trains. Every journey plugs directly into Waypoint for automatic disruption concierge.
        </p>
        <button type="button" className="link" onClick={fillExample}>
          Fill an example
        </button>
      </div>

      <div className="jr-demo-note" role="note">
        Demo data: availability and fares are simulated.
      </div>

      <form onSubmit={handleSearch}>
        <section>
          <h4>Route</h4>
          <div className="two">
            <label>
              From station
              {stations.length > 0 ? (
                <select
                  className="text"
                  value={from}
                  onChange={(e) => setFrom(e.target.value)}
                  aria-label="From station"
                >
                  <option value="">Select origin station</option>
                  {stations.map((s) => (
                    <option key={s.code} value={s.code}>
                      {s.name + " (" + s.code + ")"}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="text"
                  value={from}
                  onChange={(e) => setFrom(e.target.value.toUpperCase())}
                  placeholder="e.g. NDLS"
                  maxLength={5}
                  aria-label="From station code"
                />
              )}
            </label>

            <label>
              To station
              {stations.length > 0 ? (
                <select
                  className="text"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                  aria-label="To station"
                >
                  <option value="">Select destination station</option>
                  {stations.map((s) => (
                    <option key={s.code} value={s.code}>
                      {s.name + " (" + s.code + ")"}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="text"
                  value={to}
                  onChange={(e) => setTo(e.target.value.toUpperCase())}
                  placeholder="e.g. UJN"
                  maxLength={5}
                  aria-label="To station code"
                />
              )}
            </label>
          </div>
          {stationsError && (
            <small className="muted">
              Could not load full station list. You can enter station codes directly.
            </small>
          )}

          <div className="two">
            <label>
              Journey date
              <input
                type="date"
                className="text"
                min={todayStr()}
                value={date}
                onChange={(e) => setDate(e.target.value)}
                aria-label="Journey date"
              />
            </label>

            <label>
              {"Budget (\u20b9)"}
              <input
                type="number"
                inputMode="numeric"
                className="text"
                min="1"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                placeholder="2000"
                aria-label="Budget in rupees"
              />
            </label>
          </div>

          <button
            type="submit"
            className="btn primary jr-search-btn"
            disabled={searching || !from || !to || from === to || !date || !budget}
          >
            {searching ? "Searching trains..." : "Search trains"}
          </button>
        </section>
      </form>

      {/* Loading state */}
      {searching && (
        <div className="jr-loading">
          <p className="sub">Finding available trains...</p>
        </div>
      )}

      {/* Results */}
      {!searching && results && (
        <>
          {results.trains.length === 0 ? (
            <div className="empty">
              <h3>No trains found</h3>
              <p>Try searching for a different date or station pair.</p>
            </div>
          ) : (
            <>
              {/* Recommendation Strip */}
              {results.recommendations && (
                <section className="jr-recs-section">
                  <h4>Top recommendations</h4>
                  <div className="jr-recs-strip">
                    {[
                      { key: "best_value", label: "Best value", rec: results.recommendations.best_value },
                      { key: "fastest", label: "Fastest", rec: results.recommendations.fastest },
                      { key: "most_comfortable", label: "Most comfortable", rec: results.recommendations.most_comfortable },
                    ].map(({ key, label, rec }) => {
                      if (!rec) return null;
                      const isSelected = selected && selected.train_no === rec.train_no && selected.cls === rec.cls;
                      return (
                        <button
                          type="button"
                          key={key}
                          className={"jr-rec-card " + (isSelected ? "on" : "")}
                          onClick={() => handleSelectRec(rec)}
                          aria-pressed={isSelected}
                        >
                          <span className="jr-rec-badge">{label}</span>
                          <b>{rec.train_name}</b>
                          <div className="jr-rec-fare">
                            <span>{rec.cls}</span>
                            <span>{" \u00b7 "}</span>
                            <b>{inr(rec.fare)}</b>
                          </div>
                          <p className="sub jr-rec-reason">{rec.reason}</p>
                        </button>
                      );
                    })}
                  </div>
                </section>
              )}

              {/* Trains List */}
              <section className="jr-trains-section">
                <h4>{"Available trains (" + results.trains.length + ")"}</h4>
                {results.trains.map((t) => (
                  <div className="item jr-train-card" key={t.train_no}>
                    <div className="jr-train-head">
                      <div>
                        <b>{t.name}</b>
                        <small className="muted">{" #" + t.train_no}</small>
                      </div>
                      {t.badge && <span className="chip good">{t.badge}</span>}
                    </div>

                    <div className="jr-train-times">
                      <span><b>{t.departure}</b> <small>dep</small></span>
                      <span className="jr-arrow">{"\u2192"}</span>
                      <span><b>{t.arrival}</b> <small>arr</small></span>
                      <span className="muted jr-dur">{"(" + t.duration + ")"}</span>
                    </div>

                    <div
                      className="jr-chips-row"
                      role="radiogroup"
                      aria-label={"Classes for " + t.name}
                    >
                      {t.classes.map((c) => {
                        const isWL = c.availability.startsWith("WL") || !c.available;
                        const isSelected = selected && selected.train_no === t.train_no && selected.cls === c.cls;

                        if (isWL) {
                          return (
                            <button
                              key={c.cls}
                              type="button"
                              disabled
                              aria-disabled="true"
                              className="jr-chip jr-chip-wl"
                              title="Waitlist - cannot be booked"
                            >
                              <span className="jr-chip-cls">{c.cls}</span>
                              <span className="jr-chip-fare">{inr(c.fare)}</span>
                              <small className="jr-chip-avail">Waitlist</small>
                            </button>
                          );
                        }

                        return (
                          <button
                            key={c.cls}
                            type="button"
                            role="radio"
                            aria-pressed={isSelected}
                            className={
                              "jr-chip " +
                              (c.within_budget ? "jr-chip-good" : "jr-chip-over") +
                              (isSelected ? " on" : "")
                            }
                            onClick={() =>
                              setSelected({
                                train_no: t.train_no,
                                cls: c.cls,
                                fare: c.fare,
                                train_name: t.name,
                                availability: c.availability,
                                within_budget: c.within_budget,
                              })
                            }
                          >
                            <span className="jr-chip-cls">{c.cls}</span>
                            <span className="jr-chip-fare">{inr(c.fare)}</span>
                            <small className="jr-chip-avail">{c.availability}</small>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </section>

              {/* Selection Summary and Book button */}
              {selected && (
                <div className="jr-summary-bar">
                  <div className="jr-summary-info">
                    <b>{selected.train_name + ", " + selected.cls + ", " + inr(selected.fare)}</b>
                    <span>
                      <span className={"chip " + (selected.within_budget ? "good" : "warn")}>
                        {selected.within_budget ? "Within budget" : "Over budget"}
                      </span>
                      {" \u00b7 " + selected.availability}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn primary"
                    disabled={bookingBusy}
                    onClick={handleBookClick}
                  >
                    {bookingBusy ? "Booking..." : "Book"}
                  </button>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}


import { useEffect, useState } from "react";
import { get, inr, post } from "../api.js";
import { useUI } from "../ui.js";

/**
 * Start a journey: search real-time trains via RailRadar or flights via HasData,
 * review timings, delay status, classes, IRCTC fares, and seat availability,
 * and book with inline Book & Pay right under the selected travel option.
 */
export default function StartJourney({ onDone }) {
  const ui = useUI();

  const [mode, setMode] = useState("train"); // "train" | "flight"
  const [railStations, setRailStations] = useState([]);
  const [airports, setAirports] = useState([]);
  const [stationsError, setStationsError] = useState(false);

  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [date, setDate] = useState("");
  const [budget, setBudget] = useState("");

  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState(null);
  const [selected, setSelected] = useState(null);
  const [bookingBusy, setBookingBusy] = useState(false);

  // Load available railway stations AND airports on mount
  useEffect(() => {
    get("/api/journey/stations?mode=train")
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setRailStations(data);
        } else {
          setStationsError(true);
        }
      })
      .catch(() => setStationsError(true));

    get("/api/journey/airports")
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setAirports(data);
        }
      })
      .catch(() => {});
  }, []);

  const todayStr = () => new Date().toISOString().slice(0, 10);

  // Active locations list depending on active travel mode
  const currentLocations = mode === "train" ? railStations : airports;

  // Handle switching between Train and Flight
  const handleModeSwitch = (newMode) => {
    if (newMode === mode) return;
    setMode(newMode);
    setResults(null);
    setSelected(null);
    setFrom("");
    setTo("");
    setBudget(newMode === "flight" ? "5000" : "2000");
  };

  // "Fill an example" link dynamically adapted per mode
  const fillExample = () => {
    const d = new Date();
    d.setDate(d.getDate() + 3);
    const dateStr = d.toISOString().slice(0, 10);
    setDate(dateStr);
    if (mode === "flight") {
      setFrom("DEL");
      setTo("BOM");
      setBudget("5000");
    } else {
      setFrom("NDLS");
      setTo("UJN");
      setBudget("2000");
    }
  };

  const handleSearch = async (e) => {
    if (e) e.preventDefault();
    const cleanFrom = from.trim().toUpperCase();
    const cleanTo = to.trim().toUpperCase();
    const numBudget = Number(budget);

    if (!cleanFrom || !cleanTo) {
      return ui.toast(
        mode === "train"
          ? "Please specify both origin and destination railway stations."
          : "Please specify both departure and arrival airports."
      );
    }
    if (cleanFrom === cleanTo) {
      return ui.toast("Origin and destination must be different.");
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
        `/api/journey/search?from=${encodeURIComponent(cleanFrom)}&to=${encodeURIComponent(cleanTo)}&date=${encodeURIComponent(date)}&budget=${encodeURIComponent(numBudget)}&mode=${encodeURIComponent(mode)}&limit=10`
      );
      setResults(data);
    } catch (err) {
      ui.toast(err.message);
    } finally {
      setSearching(false);
    }
  };

  // ------------------ TRAIN BOOKING ------------------
  const executeTrainBooking = async (confirmOverBudget = false) => {
    if (!selected || bookingBusy) return;
    setBookingBusy(true);

    try {
      const paypalStatus = await get(`/api/members/${ui.memberId}/paypal`);
      if (!paypalStatus || !paypalStatus.saved) {
        ui.toast("Save PayPal first in Profile > Payments.");
        setBookingBusy(false);
        return;
      }

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

  const handleTrainBookClick = async () => {
    if (!selected || bookingBusy) return;

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
                executeTrainBooking(true);
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
      executeTrainBooking(false);
    }
  };

  // ------------------ FLIGHT BOOKING ------------------
  const executeFlightBooking = async (flight, confirmOverBudget = false) => {
    if (!flight || bookingBusy) return;
    setBookingBusy(true);

    try {
      const paypalStatus = await get(`/api/members/${ui.memberId}/paypal`);
      if (!paypalStatus || !paypalStatus.saved) {
        ui.toast("Save PayPal first in Profile > Payments.");
        setBookingBusy(false);
        return;
      }

      await post("/api/trips", {
        member_id: ui.memberId,
        title: `${flight.from_name || flight.from} to ${flight.to_name || flight.to} Flight`,
        destination: flight.to,
        purpose_type: "leisure",
        purpose_place: flight.to_name || flight.to,
        transports: [
          {
            kind: "FLIGHT",
            origin: flight.from,
            destination: flight.to,
            name: `${flight.name} (${results.date})`,
            price: flight.fare,
          },
        ],
        hotels: [],
      });

      ui.toast("Flight booked and trip added: " + flight.name);
      if (onDone) onDone();
    } catch (err) {
      ui.toast(err.message);
    } finally {
      setBookingBusy(false);
    }
  };

  const handleFlightBookClick = async (flight) => {
    if (!flight || bookingBusy) return;
    setSelected({ type: "flight", flight_no: flight.flight_no, ...flight });

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

    if (flight.fare > results.budget) {
      ui.openSheet(
        "Over budget confirmation",
        <div className="jr-confirm-sheet">
          <p className="sub">
            {"This airfare is over your budget of " + inr(results.budget) + ". Book anyway?"}
          </p>
          <div className="two" style={{ marginTop: 14 }}>
            <button
              type="button"
              className="btn primary"
              disabled={bookingBusy}
              onClick={() => {
                ui.closeSheet();
                executeFlightBooking(flight, true);
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
      executeFlightBooking(flight, false);
    }
  };

  const handleSelectTrainRec = (rec) => {
    if (!results || !results.trains) return;
    const train = results.trains.find((t) => t.train_no === rec.train_no);
    const clsInfo = train ? train.classes.find((c) => c.cls === rec.cls) : null;
    const isWL = clsInfo && (clsInfo.availability.startsWith("WL") || !clsInfo.available);
    if (isWL) {
      ui.toast("This class is on waitlist and cannot be booked.");
      return;
    }

    setSelected({
      type: "train",
      train_no: rec.train_no,
      cls: rec.cls,
      fare: rec.fare,
      train_name: rec.train_name,
      availability: clsInfo ? clsInfo.availability : "",
      within_budget: clsInfo ? clsInfo.within_budget : rec.fare <= results.budget,
    });
  };

  const handleSelectFlightRec = (rec) => {
    if (!results || !results.flights) return;
    const flight = results.flights.find((f) => f.flight_no === rec.flight_no);
    if (flight) {
      setSelected({ type: "flight", flight_no: flight.flight_no, ...flight });
    }
  };

  return (
    <div className="nt">
      <div className="ntop">
        <div>
          <h4>Start a New Journey</h4>
          <p className="sub">
            {mode === "train"
              ? "Search real-time trains, verified IRCTC fares, seat availability, and live delay tracking."
              : "Search live flights, airline schedules, and verified real-time ticket fares."}
          </p>
        </div>
        <button type="button" className="link" onClick={fillExample}>
          {mode === "train" ? "Fill NDLS \u2192 UJN example" : "Fill DEL \u2192 BOM example"}
        </button>
      </div>

      {/* Travel Mode Toggle */}
      <div className="jr-mode-switch" role="tablist" aria-label="Travel mode">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "train"}
          className={"jr-mode-btn " + (mode === "train" ? "on" : "")}
          onClick={() => handleModeSwitch("train")}
        >
          🚆 Trains ({railStations.length > 0 ? railStations.length : "94"} Stations)
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "flight"}
          className={"jr-mode-btn " + (mode === "flight" ? "on" : "")}
          onClick={() => handleModeSwitch("flight")}
        >
          ✈️ Flights ({airports.length > 0 ? airports.length : "48"} Airports)
        </button>
      </div>

      <form onSubmit={handleSearch}>
        <section>
          <h4>{mode === "train" ? "Railway Stations" : "Airports & Cities"}</h4>
          <div className="two">
            <label>
              {mode === "train" ? "From Station" : "Origin Airport / City"}
              {currentLocations.length > 0 ? (
                <select
                  className="text"
                  value={from}
                  onChange={(e) => setFrom(e.target.value)}
                  aria-label={mode === "train" ? "From railway station" : "From airport"}
                >
                  <option value="">
                    {mode === "train" ? "Select origin railway station" : "Select departure airport"}
                  </option>
                  {currentLocations.map((s) => (
                    <option key={s.code} value={s.code}>
                      {s.name}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="text"
                  value={from}
                  onChange={(e) => setFrom(e.target.value.toUpperCase())}
                  placeholder={mode === "train" ? "e.g. NDLS" : "e.g. DEL"}
                  maxLength={5}
                  aria-label="From code"
                />
              )}
            </label>

            <label>
              {mode === "train" ? "To Station" : "Destination Airport / City"}
              {currentLocations.length > 0 ? (
                <select
                  className="text"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                  aria-label={mode === "train" ? "To railway station" : "To airport"}
                >
                  <option value="">
                    {mode === "train" ? "Select destination railway station" : "Select arrival airport"}
                  </option>
                  {currentLocations.map((s) => (
                    <option key={s.code} value={s.code}>
                      {s.name}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="text"
                  value={to}
                  onChange={(e) => setTo(e.target.value.toUpperCase())}
                  placeholder={mode === "train" ? "e.g. UJN" : "e.g. BOM"}
                  maxLength={5}
                  aria-label="To code"
                />
              )}
            </label>
          </div>
          {stationsError && (
            <small className="muted">
              Could not load full locations list. You can enter codes directly (e.g. NDLS, UJN, DEL, BOM).
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
                placeholder={mode === "flight" ? "5000" : "2000"}
                aria-label="Budget in rupees"
              />
            </label>
          </div>

          <button
            type="submit"
            className="btn primary jr-search-btn"
            disabled={searching || !from || !to || from === to || !date || !budget}
          >
            {searching
              ? `Searching ${mode === "train" ? "live trains" : "flights"}...`
              : `Search ${mode === "train" ? "trains" : "flights"}`}
          </button>
        </section>
      </form>

      {/* Loading state */}
      {searching && (
        <div className="jr-loading">
          <p className="sub">
            {mode === "train"
              ? "Checking RailRadar timetables and calculating IRCTC fares..."
              : "Checking Google Flights for live schedules and ticket prices..."}
          </p>
        </div>
      )}

      {/* Results */}
      {!searching && results && (
        <>
          {/* Real-time Status Banner */}
          {results.is_live ? (
            <div className="jr-live-note" role="status">
              <span>⚡</span>
              <span>
                <b>Live Updates:</b> Real-time data powered by{" "}
                {results.source === "railradar" ? "RailRadar (Indian Railways)" : "HasData (Google Flights)"}.
              </span>
            </div>
          ) : (
            <div className="jr-demo-note" role="note">
              Simulation mode: showing schedule and IRCTC fare estimates.
            </div>
          )}

          {/* TRAIN MODE RESULTS */}
          {results.mode !== "flight" && (
            <>
              {results.trains.length === 0 ? (
                <div className="empty">
                  <h3>No trains found</h3>
                  <p>Try searching for a different date or station pair.</p>
                </div>
              ) : (
                <>
                  {/* Top Recommendation Strip */}
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
                          const isSelected =
                            selected &&
                            selected.type === "train" &&
                            selected.train_no === rec.train_no &&
                            selected.cls === rec.cls;
                          return (
                            <button
                              type="button"
                              key={key}
                              className={"jr-rec-card " + (isSelected ? "on" : "")}
                              onClick={() => handleSelectTrainRec(rec)}
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

                  {/* Available Trains List */}
                  <section className="jr-trains-section">
                    <h4>{"Available trains (" + results.trains.length + " options)"}</h4>
                    {results.trains.map((t) => {
                      const isTrainSelected =
                        selected && selected.type === "train" && selected.train_no === t.train_no;

                      return (
                        <div
                          className={"item jr-train-card " + (isTrainSelected ? "selected-card" : "")}
                          key={t.train_no}
                        >
                          {/* Header: Name, Train Number, Badges */}
                          <div className="jr-train-head">
                            <div>
                              <b>{t.name}</b>
                              <small className="muted">{" #" + t.train_no}</small>
                              <div className="jr-train-stations">
                                <span>{t.from_name || t.from}</span>
                                <span>{" \u2192 "}</span>
                                <span>{t.to_name || t.to}</span>
                              </div>
                            </div>
                            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                              {t.badge && <span className="chip good">{t.badge}</span>}
                              {t.live_status && (
                                <span className={"jr-pill " + (t.delay_minutes > 0 ? "warn" : "live")}>
                                  {t.live_status}
                                </span>
                              )}
                            </div>
                          </div>

                          {/* Timing Row: Departure, Arrival, Duration, Distance */}
                          <div className="jr-train-times">
                            <span><b>{t.departure}</b> <small>dep</small></span>
                            <span className="jr-arrow">{"\u2192"}</span>
                            <span><b>{t.arrival}</b> <small>arr</small></span>
                            {t.day_str && <span className="muted jr-dur">{t.day_str}</span>}
                            <span className="muted jr-dur">{"(" + t.duration + ")"}</span>
                            {t.distance_km && (
                              <span className="jr-pill" style={{ marginLeft: "auto" }}>
                                {t.distance_km + " km"}
                              </span>
                            )}
                          </div>

                          {/* Running Days */}
                          {t.running_days && t.running_days.length > 0 && (
                            <div className="jr-train-meta">
                              <span className="jr-pill">
                                {"Runs: " + (t.running_days.length === 7 ? "Daily" : t.running_days.join(", "))}
                              </span>
                            </div>
                          )}

                          {/* Class Berths and Availability Options */}
                          <div
                            className="jr-chips-row"
                            role="radiogroup"
                            aria-label={"Classes for " + t.name}
                          >
                            {t.classes.map((c) => {
                              const isWL = c.availability.startsWith("WL") || !c.available;
                              const isClassSelected =
                                isTrainSelected && selected.cls === c.cls;

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
                                  aria-pressed={isClassSelected}
                                  className={
                                    "jr-chip " +
                                    (c.within_budget ? "jr-chip-good" : "jr-chip-over") +
                                    (isClassSelected ? " on" : "")
                                  }
                                  onClick={() =>
                                    setSelected({
                                      type: "train",
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

                          {/* INLINE BOOK BUTTON: DIRECTLY UNDER THIS TRAIN OPTION */}
                          {isTrainSelected && (
                            <div className="jr-inline-book-box">
                              <div className="jr-inline-book-info">
                                <b>
                                  {selected.train_name} · {selected.cls} Class · {inr(selected.fare)}
                                </b>
                                <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 2 }}>
                                  <span className={"chip " + (selected.within_budget ? "good" : "warn")}>
                                    {selected.within_budget ? "Within budget" : "Over budget"}
                                  </span>
                                  <small className="muted">{selected.availability}</small>
                                </div>
                              </div>
                              <button
                                type="button"
                                className="btn primary"
                                disabled={bookingBusy}
                                onClick={handleTrainBookClick}
                              >
                                {bookingBusy ? "Booking..." : "Book & Pay (" + inr(selected.fare) + ")"}
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </section>
                </>
              )}
            </>
          )}

          {/* FLIGHT MODE RESULTS */}
          {results.mode === "flight" && (
            <>
              {(!results.flights || results.flights.length === 0) ? (
                <div className="empty">
                  <h3>No flights found</h3>
                  <p>Check origin/destination airport codes (e.g. DEL, BOM, BLR).</p>
                </div>
              ) : (
                <>
                  {/* Top Flight Recommendations */}
                  {results.recommendations && (
                    <section className="jr-recs-section">
                      <h4>Top flight recommendations</h4>
                      <div className="jr-recs-strip">
                        {[
                          { key: "best_value", label: "Best value", rec: results.recommendations.best_value },
                          { key: "fastest", label: "Fastest", rec: results.recommendations.fastest },
                        ].map(({ key, label, rec }) => {
                          if (!rec) return null;
                          const isSelected =
                            selected &&
                            selected.type === "flight" &&
                            selected.flight_no === rec.flight_no;
                          return (
                            <button
                              type="button"
                              key={key}
                              className={"jr-rec-card " + (isSelected ? "on" : "")}
                              onClick={() => handleSelectFlightRec(rec)}
                              aria-pressed={isSelected}
                            >
                              <span className="jr-rec-badge">{label}</span>
                              <b>{rec.name}</b>
                              <div className="jr-rec-fare">
                                <b>{inr(rec.fare)}</b>
                              </div>
                              <p className="sub jr-rec-reason">{rec.reason}</p>
                            </button>
                          );
                        })}
                      </div>
                    </section>
                  )}

                  {/* Flight Options List */}
                  <section className="jr-trains-section">
                    <h4>{"Available flights (" + results.flights.length + " options)"}</h4>
                    {results.flights.map((f) => {
                      const isFlightSelected =
                        selected && selected.type === "flight" && selected.flight_no === f.flight_no;

                      return (
                        <div
                          className={"item jr-train-card " + (isFlightSelected ? "selected-card" : "")}
                          key={f.flight_no}
                        >
                          <div className="jr-train-head">
                            <div>
                              <b>{f.name}</b>
                              <small className="muted">{" #" + f.flight_no}</small>
                              <div className="jr-train-stations">
                                <span>{f.from_name || f.from}</span>
                                <span>{" \u2192 "}</span>
                                <span>{f.to_name || f.to}</span>
                              </div>
                            </div>
                            <div>
                              <span className={"chip " + (f.within_budget ? "good" : "warn")}>
                                {inr(f.fare)}
                              </span>
                            </div>
                          </div>

                          <div className="jr-train-times">
                            <span><b>{f.departure}</b> <small>dep</small></span>
                            <span className="jr-arrow">{"\u2192"}</span>
                            <span><b>{f.arrival}</b> <small>arr</small></span>
                            <span className="muted jr-dur">{"(" + f.duration + ")"}</span>
                            <span className="jr-pill brand" style={{ marginLeft: "auto" }}>
                              {f.stops_label}
                            </span>
                          </div>

                          <div className="jr-train-meta">
                            <span className="jr-pill live">
                              {results.is_live ? "Live Google Flights Price" : "Simulated Airfare"}
                            </span>
                            <span className={"jr-pill " + (f.within_budget ? "live" : "warn")}>
                              {f.within_budget ? "Within budget" : "Over budget"}
                            </span>
                          </div>

                          {/* INLINE BOOK BUTTON: DIRECTLY UNDER THIS FLIGHT OPTION */}
                          <div className="jr-inline-book-box">
                            <div className="jr-inline-book-info">
                              <b>{f.name} · {inr(f.fare)}</b>
                              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                                <span className={"chip " + (f.within_budget ? "good" : "warn")}>
                                  {f.within_budget ? "Within budget" : "Over budget"}
                                </span>
                                <small className="muted">{f.stops_label}</small>
                              </div>
                            </div>
                            <button
                              type="button"
                              className="btn primary"
                              disabled={bookingBusy}
                              onClick={() => handleFlightBookClick(f)}
                            >
                              {bookingBusy && selected?.flight_no === f.flight_no
                                ? "Booking..."
                                : "Book Flight (" + inr(f.fare) + ")"}
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </section>
                </>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

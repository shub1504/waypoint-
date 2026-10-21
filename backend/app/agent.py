"""The disruption agent.

handle_event()  : a disruption arrives -> find alternatives -> check guardrails -> act or ask.
approve()/choose(): the member answers when the agent had to stop and ask.

The decision itself is deterministic (guardrail + relevance + scoring). An LLM, if configured,
is only used afterwards to phrase the message the member reads (see notify.py), so a model
mistake can never overspend a card member's money.
"""
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import guardrail, inventory, notify, relevance
from app.models import Booking, Decision, DisruptionEvent, Member, Trip, utcnow

TRANSPORT_KINDS = {"FLIGHT", "TRAIN", "BUS"}


def _money(x: float) -> str:
    return f"₹{x:,.0f}"


def _norm(v: float, lo: float, hi: float) -> float:
    return 1.0 if hi == lo else (v - lo) / (hi - lo)


def _active_booking(session: Session, booking_id: str) -> Booking | None:
    """Follow the rebooking chain so a stale event still lands on the live booking."""
    b = session.get(Booking, booking_id)
    while b is not None and b.status == "REBOOKED":
        b = session.scalar(select(Booking).where(Booking.replaces_id == b.id))
    return b


def _committed_others(session: Session, trip_id: str, exclude_id: str) -> float:
    rows = session.scalars(
        select(Booking).where(Booking.trip_id == trip_id, Booking.status == "ACTIVE", Booking.id != exclude_id)
    ).all()
    return sum(r.amount for r in rows)


def _release_hotel_night(session: Session, trip: Trip) -> float:
    """A long delay means a hotel night goes unused; the saving joins the trip's budget pool."""
    hotel = session.scalar(
        select(Booking).where(Booking.trip_id == trip.id, Booking.kind == "HOTEL", Booking.status == "ACTIVE")
    )
    if hotel is None or not hotel.nights or hotel.nights < 2:
        return 0.0
    saved = hotel.price_per_night or 0.0
    hotel.nights -= 1
    hotel.amount -= saved
    trip.pool_credit += saved
    return saved


def _decision(event: DisruptionEvent, member: Member, booking: Booking, ceiling: float, **kw) -> Decision:
    return Decision(
        event_id=event.event_id, member_id=member.id, trip_id=booking.trip_id, booking_id=booking.id,
        event_type=event.type, kind=booking.kind, payment_type=booking.payment_type,
        original_amount=booking.baseline_amount, ceiling=ceiling, channel=member.alert_channel, **kw,
    )


def _apply(session: Session, old: Booking, option: dict) -> Booking:
    """Replace the disrupted booking with the chosen option."""
    old.status = "REBOOKED"
    n = len(session.scalars(select(Booking).where(Booking.trip_id == old.trip_id)).all()) + 1
    new = Booking(
        id=f"{old.trip_id}-R{n}", trip_id=old.trip_id, kind=option["kind"], payment_type=old.payment_type,
        amount=option["total_cost"], baseline_amount=old.baseline_amount,
        origin=option.get("origin", old.origin), destination=option.get("destination", old.destination),
        label=option["label"], hotel_area=option.get("area"), distance_km=option.get("distance_km"),
        price_per_night=option.get("price_per_night"), nights=option.get("nights"),
        replaces_id=old.id,
    )
    session.add(new)
    return new


# ---------------------------------------------------------------- candidate builders
def _transport_options(booking: Booking, sold_out: bool) -> list[dict]:
    raw = inventory.search_transport(booking.kind, booking.origin, booking.destination, sold_out, booking.baseline_amount)
    return [
        dict(kind=booking.kind, origin=booking.origin, destination=booking.destination,
             label=f"{o['name']} {booking.origin}→{booking.destination}", total_cost=float(o["price"]),
             depart_in_h=o["depart_in_h"], duration_h=o["duration_h"], seats=o["seats"])
        for o in raw if o["name"] not in booking.label
    ]


def _hotel_options(booking: Booking, trip: Trip, pref: dict) -> list[dict]:
    nights = booking.nights or 1
    out = []
    for h in inventory.search_hotels(trip.purpose_place, exclude_name=booking.label.split(" (")[0],
                                  ref_price=booking.price_per_night, area=booking.hotel_area):
        out.append(dict(
            kind="HOTEL", label=f"{h['name']} ({nights} night{'s' if nights > 1 else ''})", area=h["area"],
            distance_km=h["distance_km"], price_per_night=float(h["price"]), nights=nights,
            total_cost=float(h["price"]) * nights,
            relevance=relevance.relevance_score(h["distance_km"], h["area"], pref),
        ))
    return out


def _fallback_options(booking: Booking) -> list[dict]:
    """Slide 8: nothing from the original point -> switch mode, or try nearby departure points."""
    opts = []
    if booking.kind not in TRANSPORT_KINDS:
        return opts
    for o in ([] if booking.kind == "BUS" else inventory.search_transport("BUS", booking.origin, booking.destination, False, booking.baseline_amount)):
        opts.append(dict(kind="BUS", origin=booking.origin, destination=booking.destination,
                         label=f"Switch to bus: {o['name']}", total_cost=float(o["price"]),
                         depart_in_h=o["depart_in_h"], duration_h=o["duration_h"], via="mode switch"))
    for near in inventory.nearby_points(booking.origin):
        for o in inventory.search_transport(booking.kind, near["code"], booking.destination, False, booking.baseline_amount):
            opts.append(dict(
                kind=booking.kind, origin=near["code"], destination=booking.destination,
                label=f"Depart from {near['name']}: {o['name']} (+ cab {_money(near['cab_cost'])})",
                total_cost=float(o["price"] + near["cab_cost"]),  # extra local leg is counted
                depart_in_h=o["depart_in_h"] + near["cab_h"], duration_h=o["duration_h"],
                via="nearby departure", extra_leg_cost=float(near["cab_cost"]),
            ))
    return opts


# ---------------------------------------------------------------- main entry point
def handle_event(session: Session, payload: dict) -> Decision | None:
    event = DisruptionEvent(
        event_id=payload["event_id"], type=payload["type"], member_id=payload["member_id"],
        trip_id=payload["trip_id"], booking_id=payload["booking_id"],
        delay_hours=float(payload.get("delay_hours", 0)), demand_spike=bool(payload.get("demand_spike", False)),
        source=payload.get("source", "simulator"),
        detected_at=datetime.fromisoformat(payload["detected_at"]).replace(tzinfo=None),
    )
    if session.get(DisruptionEvent, event.event_id):
        return None  # Event Hubs is at-least-once: ignore a duplicate delivery
    session.add(event)

    member = session.get(Member, event.member_id)
    trip = session.get(Trip, event.trip_id)
    booking = _active_booking(session, event.booking_id)
    if member is None or trip is None or booking is None or booking.status != "ACTIVE":
        return None  # unknown, or the member already cancelled it

    saved = 0.0
    if event.type != "HOTEL_OVERBOOKED" and event.delay_hours >= 24:
        saved = _release_hotel_night(session, trip)

    committed = _committed_others(session, trip.id, booking.id)
    level = member.budget_level
    ceiling = guardrail.ceiling_for(booking.baseline_amount, booking.payment_type, level)

    def verdict(cost: float) -> guardrail.Verdict:
        return guardrail.evaluate(cost, booking.baseline_amount, booking.payment_type, level,
                                  trip.pool_credit, committed, trip.envelope, member.consent_autorebook)

    notes = []
    if saved:
        notes.append(f"Delay of {event.delay_hours:.0f}h freed one hotel night, adding {_money(saved)} to the trip budget pool.")

    pref = None
    if booking.kind == "HOTEL":
        pref = relevance.learn_preference(
            session, member.id, trip.purpose_type, booking.distance_km, booking.hotel_area
        ) if member.consent_history else {"pref_distance_km": booking.distance_km or 1.0,
                                           "pref_area": booking.hotel_area, "samples": 0, "source": "original booking"}
        options = _hotel_options(booking, trip, pref)
        notes.append(f"Preferred stay: ~{pref['pref_distance_km']} km from {trip.purpose_place}, "
                     f"{pref['pref_area']} ({pref['samples']} past stays).")
        options = [o for o in options if o["relevance"] >= relevance.MIN_RELEVANCE] or options
    else:
        options = _transport_options(booking, event.demand_spike)

    # ---- no availability at all -> fallback choice (slide 8)
    if not options:
        fb = _fallback_options(booking)
        for o in fb:
            v = verdict(o["total_cost"])
            o["within_guardrail"] = v.allowed
            o["guardrail_note"] = v.reason
        d = _decision(event, member, booking, ceiling, status="FALLBACK_OPTIONS",
                      reasoning=" ".join(notes + [
                          "No tickets available from the original departure point. "
                          "Choose a different mode, or let the agent depart from a nearby station."]),
                      options_json=json.dumps(fb))
        return _finish(session, event, member, trip, booking, d)

    scored = []
    for o in options:
        o["verdict"] = verdict(o["total_cost"]).as_dict()
        scored.append(o)
    allowed = [o for o in scored if o["verdict"]["allowed"]]

    if allowed:
        _score(allowed, booking.kind)
        best = max(allowed, key=lambda o: o["score"])
        v = best["verdict"]
        auto = booking.payment_type == "PAY_AFTER" or member.consent_autorebook
        notes.append(f"Chose {best['label']}: {v['reason']}.")
        d = _decision(event, member, booking, ceiling,
                      status="AUTO_BOOKED" if auto else "NEEDS_APPROVAL",
                      pool_credit_used=v["pool_used"], reasoning=" ".join(notes),
                      chosen_amount=best["total_cost"], chosen_label=best["label"],
                      chosen_json=json.dumps(best), options_json=json.dumps(_slim(scored)))
        if auto:
            session.flush()
            _apply(session, booking, best)
            trip.pool_credit = max(0.0, trip.pool_credit - v["pool_used"])
        return _finish(session, event, member, trip, booking, d)

    # ---- everything available is above the limit -> never auto-book, ask the member
    cheapest = min(scored, key=lambda o: o["total_cost"] if booking.kind != "HOTEL" else -o["relevance"] * 1e6 + o["total_cost"])
    notes.append(f"Cheapest suitable option is {cheapest['label']} at {_money(cheapest['total_cost'])}; "
                 f"{cheapest['verdict']['reason']}. Not booked automatically.")
    d = _decision(event, member, booking, ceiling, status="NEEDS_APPROVAL",
                  reasoning=" ".join(notes), chosen_amount=cheapest["total_cost"],
                  chosen_label=cheapest["label"], chosen_json=json.dumps(cheapest),
                  options_json=json.dumps(_slim(scored)))
    return _finish(session, event, member, trip, booking, d)


def _score(opts: list[dict], kind: str) -> None:
    prices = [o["total_cost"] for o in opts]
    lo, hi = min(prices), max(prices)
    if kind == "HOTEL":
        for o in opts:
            o["score"] = round(0.55 * o["relevance"] + 0.45 * (1 - _norm(o["total_cost"], lo, hi)), 3)
    else:
        t = [o["depart_in_h"] for o in opts]
        tlo, thi = min(t), max(t)
        for o in opts:
            o["score"] = round(0.55 * (1 - _norm(o["total_cost"], lo, hi)) + 0.45 * (1 - _norm(o["depart_in_h"], tlo, thi)), 3)


def _slim(opts: list[dict]) -> list[dict]:
    keep = ("label", "total_cost", "depart_in_h", "area", "distance_km", "relevance", "score")
    return [{**{k: o[k] for k in keep if k in o}, "allowed": o["verdict"]["allowed"], "note": o["verdict"]["reason"]} for o in opts]


def _finish(session: Session, event: DisruptionEvent, member: Member, trip: Trip, booking: Booking, d: Decision) -> Decision:
    d.latency_ms = max(0, int((utcnow() - event.detected_at).total_seconds() * 1000))
    d.notification = notify.compose(member, trip, booking, d)
    session.add(d)
    session.flush()
    return d


# ---------------------------------------------------------------- member answers
def approve(session: Session, decision_id: int) -> Decision:
    d = session.get(Decision, decision_id)
    if d is None or d.status != "NEEDS_APPROVAL":
        raise ValueError("Decision is not waiting for approval")
    booking = _active_booking(session, d.booking_id)
    option = json.loads(d.chosen_json)
    _apply(session, booking, option)
    trip = session.get(Trip, d.trip_id)
    trip.pool_credit = max(0.0, trip.pool_credit - d.pool_credit_used)
    d.status, d.resolved_at = "USER_APPROVED", utcnow()
    return d


def decline(session: Session, decision_id: int) -> Decision:
    d = session.get(Decision, decision_id)
    if d is None or d.status not in ("NEEDS_APPROVAL", "FALLBACK_OPTIONS"):
        raise ValueError("Decision is not waiting for an answer")
    d.status, d.resolved_at = "DECLINED", utcnow()
    return d


def choose(session: Session, decision_id: int, option_index: int) -> Decision:
    d = session.get(Decision, decision_id)
    if d is None or d.status != "FALLBACK_OPTIONS":
        raise ValueError("Decision has no fallback options to choose from")
    options = json.loads(d.options_json)
    option = options[option_index]
    booking = _active_booking(session, d.booking_id)
    _apply(session, booking, option)
    d.chosen_amount, d.chosen_label, d.chosen_json = option["total_cost"], option["label"], json.dumps(option)
    d.status, d.resolved_at = "USER_CHOSE", utcnow()
    return d

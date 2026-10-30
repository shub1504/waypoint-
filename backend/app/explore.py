"""Data behind the Explore and Profile tabs.

options_payload() : every alternative for one booking, with its guardrail verdict (Explore + matrix)
switch()          : the member picks one by hand (guardrail warns, the member decides)
bookings_payload(): new vs old bookings with original-vs-replacement pairs (Profile)
"""
import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import agent, guardrail, relevance
from app.models import Booking, BookingHistory, Decision, Member, Trip, utcnow


def booking_dict(b: Booking) -> dict:
    return dict(
        id=b.id, trip_id=b.trip_id, kind=b.kind, label=b.label, amount=b.amount,
        baseline_amount=b.baseline_amount, payment_type=b.payment_type, status=b.status,
        origin=b.origin, destination=b.destination, area=b.hotel_area, distance_km=b.distance_km,
        nights=b.nights, price_per_night=b.price_per_night, replaces_id=b.replaces_id,
        created_at=b.created_at.isoformat() + "Z" if b.created_at else None,
    )


def with_limit(d: dict, b: Booking, trip: Trip, member: Member) -> dict:
    """Add what Waypoint may rebook this booking up to on its own: ceiling = original price x multiplier,
    plus whatever the trip pool has saved. Only for active bookings."""
    if b.status != "ACTIVE":
        return d
    mult = guardrail.PAY_AFTER_MULT if b.payment_type == "PAY_AFTER" else guardrail.PREPAID_MULT[member.budget_level]
    c = guardrail.ceiling_for(b.baseline_amount, b.payment_type, member.budget_level)
    return d | dict(ceiling=c, multiplier=mult, pool_credit=trip.pool_credit, auto_limit=c + trip.pool_credit)


def _context(session: Session, booking_id: str):
    booking = agent._active_booking(session, booking_id)
    if booking is None:
        raise ValueError("Unknown booking")
    trip = session.get(Trip, booking.trip_id)
    member = session.get(Member, trip.member_id)
    return booking, trip, member


def build_options(session: Session, booking_id: str):
    booking, trip, member = _context(session, booking_id)
    if booking.kind == "HOTEL":
        if member.consent_history:
            pref = relevance.learn_preference(
                session, member.id, trip.purpose_type, booking.distance_km, booking.hotel_area)
        else:
            pref = {"pref_distance_km": booking.distance_km or 1.0, "pref_area": booking.hotel_area,
                    "samples": 0, "source": "original booking"}
        opts = agent._hotel_options(booking, trip, pref)
        for o in opts:
            o["via"] = "same area"
    else:
        opts = agent._transport_options(booking, False)
        for o in opts:
            o["via"] = "same route"
        opts += agent._fallback_options(booking)  # mode switch + nearby departure = "more options"
    committed = agent._committed_others(session, trip.id, booking.id)
    for o in opts:
        o["verdict"] = guardrail.evaluate(
            o["total_cost"], booking.baseline_amount, booking.payment_type, member.budget_level,
            trip.pool_credit, committed, trip.envelope, member.consent_autorebook).as_dict()
    if opts:
        agent._score(opts, booking.kind)
    return booking, trip, member, opts


def options_payload(session: Session, booking_id: str) -> dict:
    booking, trip, member, opts = build_options(session, booking_id)
    out = []
    for o in opts:
        v = o["verdict"]
        out.append(dict(
            key=o["label"], label=o["label"], kind=o["kind"], via=o.get("via"),
            total_cost=o["total_cost"], delta=o["total_cost"] - booking.amount,
            depart_in_h=o.get("depart_in_h"), duration_h=o.get("duration_h"),
            area=o.get("area"), distance_km=o.get("distance_km"), relevance=o.get("relevance"),
            score=o.get("score"), allowed=v["allowed"], reason=v["reason"], pool_used=v["pool_used"],
            extra_leg_cost=o.get("extra_leg_cost"),
        ))
    out.sort(key=lambda x: (not x["allowed"], -(x["score"] or 0)))
    ceiling = guardrail.ceiling_for(booking.baseline_amount, booking.payment_type, member.budget_level)
    return dict(booking=booking_dict(booking), ceiling=ceiling, limit=ceiling + trip.pool_credit,
                pool_credit=trip.pool_credit, purpose=trip.purpose_place, options=out)


def switch(session: Session, booking_id: str, label: str) -> Decision:
    booking, trip, member, opts = build_options(session, booking_id)
    chosen = next((o for o in opts if o["label"] == label), None)
    if chosen is None:
        raise ValueError("That option is no longer available")
    v = chosen["verdict"]
    ceiling = guardrail.ceiling_for(booking.baseline_amount, booking.payment_type, member.budget_level)
    note = (f"You switched manually to {label}. {v['reason']}." if v["allowed"]
            else f"You switched manually to {label}. Heads up: {v['reason']}; you approved it yourself.")
    d = Decision(
        event_id=f"manual-{uuid.uuid4().hex[:8]}", member_id=member.id, trip_id=trip.id, booking_id=booking.id,
        event_type="MANUAL_SWITCH", status="USER_CHOSE", kind=booking.kind, payment_type=booking.payment_type,
        original_amount=booking.baseline_amount, ceiling=ceiling,
        pool_credit_used=v["pool_used"] if v["allowed"] else 0.0,
        chosen_amount=chosen["total_cost"], chosen_label=label, chosen_json=json.dumps(chosen),
        options_json=json.dumps(agent._slim(opts)), reasoning=note,
        notification=f"You switched to {label} for ₹{chosen['total_cost']:,.0f}.",
        channel=member.alert_channel, latency_ms=0, resolved_at=utcnow(),
    )
    agent._need_paypal_on_file(session, booking, member.id)
    new = agent._apply(session, booking, chosen)
    pay_msg = agent._collect_payment(session, booking, new)
    if pay_msg:
        d.notification = f"{d.notification} {pay_msg}".strip()
    if v["allowed"]:
        trip.pool_credit = max(0.0, trip.pool_credit - v["pool_used"])
    session.add(d)
    session.flush()
    return d


def _decision_summary(session: Session, booking_id: str) -> dict | None:
    d = session.scalar(select(Decision).where(Decision.booking_id == booking_id).order_by(Decision.id.desc()))
    if d is None:
        return None
    return dict(id=d.id, status=d.status, latency_ms=d.latency_ms, reasoning=d.reasoning,
                ceiling=d.ceiling, pool_credit_used=d.pool_credit_used,
                by="You" if d.status in ("USER_APPROVED", "USER_CHOSE") else "Agent")


def bookings_payload(session: Session, member_id: str) -> dict:
    member = session.get(Member, member_id)
    trips = {t.id: t for t in session.scalars(select(Trip).where(Trip.member_id == member_id)).all()}
    rows = session.scalars(
        select(Booking).where(Booking.trip_id.in_(list(trips) or [""])).order_by(Booking.created_at, Booking.id)
    ).all()
    by_id = {b.id: b for b in rows}

    def root(b: Booking) -> Booking:
        while b.replaces_id and b.replaces_id in by_id:
            b = by_id[b.replaces_id]
        return b

    new, old = [], []
    for b in rows:
        t = trips[b.trip_id]
        item = with_limit(booking_dict(b), b, t, member) | dict(trip_title=t.title, purpose=t.purpose_place)
        if b.status == "ACTIVE":
            r = root(b)
            item["original"] = booking_dict(r) if r.id != b.id else None
            item["decision"] = _decision_summary(session, b.replaces_id) if b.replaces_id else None
            new.append(item)
        else:
            repl = next((x for x in rows if x.replaces_id == b.id), None)
            item["replaced_by"] = booking_dict(repl) if repl else None
            item["decision"] = _decision_summary(session, b.id)
            if b.status == "CANCELLED":
                c = session.scalar(select(Decision).where(Decision.trip_id == b.trip_id, Decision.event_type == "USER_CANCEL")
                                   .order_by(Decision.id.desc()))
                info = json.loads(c.chosen_json) if c and c.chosen_json else {}
                mine = next((i for i in info.get("items", []) if i["booking_id"] == b.id), {})
                item["cancelled"] = dict(reason=info.get("reason_label"), note=info.get("note"),
                                         refund=mine.get("refund"), refund_note=mine.get("note"))
            old.append(item)
    past = session.scalars(
        select(BookingHistory).where(BookingHistory.member_id == member_id).order_by(BookingHistory.stayed_on.desc())
    ).all()
    return dict(
        new=new, old=old[::-1],
        past_stays=[dict(id=h.id, city=h.city, purpose_type=h.purpose_type, purpose_place=h.purpose_place,
                         hotel_name=h.hotel_name, area=h.hotel_area, distance_km=h.distance_km,
                         price_per_night=h.price_per_night, stayed_on=h.stayed_on) for h in past],
    )

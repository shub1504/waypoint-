"""The member cancels a booking or a whole trip and says why; Waypoint acts on the reason.

Everything here is a fixed rule, not a model guess, so a refund promise is always explainable.
plan()  : what would happen (shown before the member confirms)
apply() : do it, record the decision, and return it so the member is notified
"""
import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import agent, explore, guardrail, payments, relevance
from app.models import Booking, Decision, Member, Trip, utcnow
from app.paypal_client import PayPalError

log = logging.getLogger("waypoint")
REASONS = {
    "plans_changed": dict(label="My plans changed",
                          does="Cancels it and applies the normal refund rules."),
    "medical": dict(label="Medical or family emergency",
                    does="Cancels it and raises a full-refund waiver claim (a doctor's note may be asked for)."),
    "event_cancelled": dict(label="Event or meeting was cancelled",
                            does="Cancels it and files an organiser-cancellation claim for almost the full amount."),
    "other": dict(label="Something else",
                  does="Cancels it with the standard refund rules. Your short reason is saved so Waypoint can learn from it."),
    "better_option": dict(label="I found a better option",
                          does="Swaps this one booking for the cheapest cheaper option inside your limit and adds the saving to your trip pool."),
}

# Share of a prepaid ticket that comes back. Hotels are pay-at-checkout, so nothing was charged yet.
_STANDARD = {"FLIGHT": 0.70, "TRAIN": 0.80, "BUS": 0.85}
_EVENT = {"FLIGHT": 0.90, "TRAIN": 0.95, "BUS": 1.00}


def _money(x: float) -> str:
    return f"₹{x:,.0f}"


def _refund_rate(b: Booking, reason: str) -> tuple[float, str]:
    if b.payment_type == "PAY_AFTER":
        return 1.0, "Nothing was charged yet, so cancelling is free"
    if reason == "medical":
        return 1.0, "Full refund requested under the emergency waiver"
    if reason == "event_cancelled":
        r = _EVENT[b.kind]
        return r, ("Full refund requested as the event was cancelled" if r == 1 else f"{r:.0%} back as an organiser-cancellation claim")
    r = _STANDARD[b.kind]
    return r, f"{r:.0%} back under the standard {b.kind.lower()} cancellation rule"


def _targets(session: Session, trip_id: str, booking_id: str | None) -> tuple[Trip, list[Booking]]:
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise ValueError("Unknown trip")
    if booking_id:
        b = session.get(Booking, booking_id)
        if b is None or b.trip_id != trip.id or b.status != "ACTIVE":
            raise ValueError("That booking is not active any more")
        return trip, [b]
    rows = session.scalars(select(Booking).where(Booking.trip_id == trip.id, Booking.status == "ACTIVE")).all()
    if not rows:
        raise ValueError("This trip has nothing left to cancel")
    return trip, list(rows)


def _best_swap(session: Session, b: Booking) -> tuple[dict | None, list[dict]]:
    _, _, _, opts = explore.build_options(session, b.id)
    ok = [o for o in opts if o["verdict"]["allowed"] and o["total_cost"] < b.amount
          and o.get("relevance", 1.0) >= relevance.MIN_RELEVANCE]
    return (min(ok, key=lambda o: o["total_cost"]) if ok else None), opts


def plan(session: Session, trip_id: str, booking_id: str | None, reason: str, note: str = "") -> dict:
    if reason not in REASONS:
        raise ValueError("Please choose a reason")
    if reason == "other" and not note.strip():
        raise ValueError("Please add a short reason (a few words)")
    trip, targets = _targets(session, trip_id, booking_id)
    out = dict(ok=True, reason=reason, reason_label=REASONS[reason]["label"], scope="booking" if booking_id else "trip",
               trip_title=trip.title, items=[], total_amount=sum(b.amount for b in targets), total_refund=0.0,
               claim=reason in ("medical", "event_cancelled"), message="", saving=0.0)
    if reason == "better_option":
        if not booking_id:
            return {**out, "ok": False, "message": "Pick one booking to swap. Cancel the whole trip with another reason."}
        b = targets[0]
        best, _ = _best_swap(session, b)
        if best is None:
            return {**out, "ok": False, "message": "There is no cheaper option inside your limit right now, so your current booking stays."}
        out.update(items=[dict(booking_id=b.id, label=b.label, amount=b.amount, refund=b.amount,
                               note=f"Replaced by {best['label']} at {_money(best['total_cost'])}")],
                   saving=b.amount - best["total_cost"], total_refund=b.amount, replacement=best["label"],
                   message=f"Swap to {best['label']} ({_money(best['total_cost'])}) and save {_money(b.amount - best['total_cost'])}, added to your trip pool.")
        return out
    for b in targets:
        rate, note = _refund_rate(b, reason)
        out["items"].append(dict(booking_id=b.id, label=b.label, kind=b.kind, amount=b.amount, refund=round(b.amount * rate), note=note))
    out["total_refund"] = sum(i["refund"] for i in out["items"])
    out["message"] = (f"{_money(out['total_refund'])} of {_money(out['total_amount'])} comes back."
                      + (" A claim is raised for the part that is not automatic." if out["claim"] else ""))
    return out


def apply(session: Session, trip_id: str, booking_id: str | None, reason: str, note: str = "") -> Decision:
    p = plan(session, trip_id, booking_id, reason, note)
    if not p["ok"]:
        raise ValueError(p["message"])
    trip, targets = _targets(session, trip_id, booking_id)
    member = session.get(Member, trip.member_id)
    first = member.name.split()[0]
    why = p["reason_label"] + (f" ({note.strip()})" if note.strip() else "")

    if reason == "better_option":
        b = targets[0]
        best, opts = _best_swap(session, b)
        ceiling = guardrail.ceiling_for(b.baseline_amount, b.payment_type, member.budget_level)
        saving = b.amount - best["total_cost"]
        agent._need_paypal_on_file(session, b, member.id)
        new = agent._apply(session, b, best)
        pay_msg = agent._collect_payment(session, b, new)
        trip.pool_credit += saving
        
        d = Decision(
            event_id=f"swap-{uuid.uuid4().hex[:8]}", member_id=member.id, trip_id=trip.id, booking_id=b.id,
            event_type="USER_SWAP", status="USER_CHOSE", kind=b.kind, payment_type=b.payment_type,
            original_amount=b.baseline_amount, ceiling=ceiling, chosen_amount=best["total_cost"],
            chosen_label=best["label"], chosen_json=json.dumps(best), options_json=json.dumps(agent._slim(opts)),
            reasoning=(f"Reason: {why}. Waypoint swapped to {best['label']}, the cheapest option that is "
                       f"cheaper than your booking and inside your limit. The {_money(saving)} saving was added to your trip pool."),
            notification=(f"Hi {first}, swapped to {best['label']} for {_money(best['total_cost'])}. "
                          f"You save {_money(saving)}, now in your trip pool for future disruptions."),
            channel=member.alert_channel, latency_ms=0, resolved_at=utcnow())
        if pay_msg:
            d.notification = f"{d.notification} {pay_msg}".strip()
        session.add(d); session.flush()
        return d

    for b in targets:
        b.status = "CANCELLED"
    pay_notes = []
    for i in p["items"]:
        try:
            r = payments.settle_cancellation(session, i["booking_id"], i["refund"])
        except PayPalError as e:
            log.warning("PayPal settlement failed for %s: %s", i["booking_id"], e)
            pay_notes.append(f"{i['label']}: the PayPal refund is still pending and will be retried.")
            continue
        if r:
            pay_notes.append(f"{i['label']}: {r['note']}")
    whole = p["scope"] == "trip"
    detail = dict(p, note=note.strip(), payments=pay_notes)
    reasoning = (f"Reason: {why}. {REASONS[reason]['does']} "
                 + " ".join(f"{i['label']}: {i['note']}." for i in p["items"])
                 + (" PayPal: " + " ".join(pay_notes) if pay_notes else ""))
    count = len(targets)
    notif = (f"Hi {first}, your trip '{trip.title}' is cancelled ({why})." if whole
             else f"Hi {first}, '{targets[0].label}' is cancelled ({why}).")
    notif += f" Expected refund {_money(p['total_refund'])} of {_money(p['total_amount'])}" + (f" across {count} bookings." if count > 1 else ".")
    if p["claim"]:
        notif += " We raised a claim for you and will ask for proof if needed."
    d = Decision(
        event_id=f"cancel-{uuid.uuid4().hex[:8]}", member_id=member.id, trip_id=trip.id, booking_id=targets[0].id,
        event_type="USER_CANCEL", status="TRIP_CANCELLED" if whole else "BOOKING_CANCELLED",
        kind="TRIP" if whole else targets[0].kind, payment_type="MIXED" if whole else targets[0].payment_type,
        original_amount=p["total_amount"], ceiling=0.0, chosen_amount=None, chosen_label=f"Refund {_money(p['total_refund'])}",
        chosen_json=json.dumps(detail), options_json=json.dumps(p["items"]), reasoning=reasoning,
        notification=notif, channel=member.alert_channel, latency_ms=0, resolved_at=utcnow())
    session.add(d); session.flush()
    return d

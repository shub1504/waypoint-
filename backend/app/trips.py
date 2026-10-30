"""Members entering their own trip: where they start, where they go, and what they already booked."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, Member, Trip

PURPOSES = ("temple", "business", "monument", "leisure")
PAYMENT = {"FLIGHT": "PREPAID", "TRAIN": "PREPAID", "BUS": "PREPAID"}


def _place(v: str) -> str:
    """Airport and station codes are matched against the demo inventory, so keep them upper-case."""
    v = v.strip()
    return v.upper() if len(v) <= 5 and v.replace(" ", "").isalpha() else v


def _next_trip_id(session: Session) -> str:
    nums = [int(m.group(1)) for tid in session.scalars(select(Trip.id)).all() if (m := re.fullmatch(r"T(\d+)", tid))]
    return f"T{max(nums, default=0) + 1}"


def create_trip(session: Session, member_id: str, data: dict) -> Trip:
    if session.get(Member, member_id) is None:
        raise ValueError("Unknown member")
    transports, hotels = data.get("transports") or [], data.get("hotels") or []
    if not transports and not hotels:
        raise ValueError("Add at least one ticket or hotel you have booked")
    destination = data["destination"].strip()
    if not destination:
        raise ValueError("Destination is required")
    tid = _next_trip_id(session)
    bookings, i = [], 0
    for t in transports:
        i += 1
        o, d = _place(t["origin"]), _place(t["destination"])
        if not o or not d:
            raise ValueError("Every ticket needs a from and a to")
        label = f"{t['name'].strip() or t['kind'].title()} {o}→{d}"
        bookings.append(Booking(
            id=f"{tid}-B{i}", trip_id=tid, kind=t["kind"], payment_type=PAYMENT[t["kind"]],
            amount=float(t["price"]), baseline_amount=float(t["price"]), origin=o, destination=d, label=label))
    for h in hotels:
        i += 1
        nights, ppn = int(h["nights"]), float(h["price_per_night"])
        name = h["name"].strip()
        if not name:
            raise ValueError("Every hotel needs a name")
        bookings.append(Booking(
            id=f"{tid}-B{i}", trip_id=tid, kind="HOTEL", payment_type="PAY_AFTER", amount=ppn * nights,
            baseline_amount=ppn * nights, label=f"{name} ({nights} night{'s' if nights > 1 else ''})",
            hotel_area=h["area"].strip() or destination, distance_km=float(h["distance_km"]),
            price_per_night=ppn, nights=nights))
    place = (data.get("purpose_place") or "").strip() or destination
    trip = Trip(id=tid, member_id=member_id, title=(data.get("title") or "").strip() or f"Trip to {destination}",
                purpose_type=data["purpose_type"], purpose_place=place, destination_city=destination,
                envelope=sum(b.amount for b in bookings), pool_credit=0.0)
    session.add(trip)
    session.add_all(bookings)
    session.flush()
    return trip

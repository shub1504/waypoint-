"""Demo scenarios: each one pushes a different slide of the deck through the live pipeline."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, Trip

SCENARIOS = {
    "flight_auto": dict(
        title="Flight cancelled → auto-rebooked within ceiling",
        slide="Spend Guardrail Engine", member="M001", kind="FLIGHT", type="FLIGHT_CANCELLED", delay_hours=3),
    "over_ceiling": dict(
        title="Flight cancelled → every option above the ceiling",
        slide="Spend Guardrail Engine", member="M003", kind="FLIGHT", type="FLIGHT_CANCELLED", delay_hours=4),
    "pool_offset": dict(
        title="Long delay → saved hotel night lifts the flight limit",
        slide="Trip Budget Pool", member="M003", kind="FLIGHT", type="FLIGHT_CANCELLED", delay_hours=30),
    "hotel_relevance": dict(
        title="Hotel overbooked → rebooked near the temple, not just cheapest",
        slide="Relevance-Aware Rebooking", member="M001", kind="HOTEL", type="HOTEL_OVERBOOKED", delay_hours=0),
    "train_sold_out": dict(
        title="Train cancelled + tickets sold out → fallback choices",
        slide="No-Availability Fallback", member="M001", kind="TRAIN", type="TRAIN_CANCELLED",
        delay_hours=0, demand_spike=True),
    "missed_connection": dict(
        title="Missed connection on a business trip (high budget)",
        slide="Spend Guardrail Engine", member="M002", kind="FLIGHT", type="MISSED_CONNECTION", delay_hours=5),
}


def _event(type_, member, trip_id, booking_id, delay_hours=0, demand_spike=False, scenario=None) -> dict:
    return dict(
        event_id=uuid.uuid4().hex[:12], type=type_, member_id=member, trip_id=trip_id, booking_id=booking_id,
        delay_hours=delay_hours, demand_spike=demand_spike, source="simulator", scenario=scenario,
        detected_at=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    )


def build_event(session: Session, scenario_id: str, member: str | None = None) -> dict | None:
    """`member` runs the scenario on someone else (used for accounts added from the app)."""
    sc = dict(SCENARIOS[scenario_id])
    if member:
        sc["member"] = member
    # the member's first trip that still has an active booking of the right kind
    for trip in session.scalars(select(Trip).where(Trip.member_id == sc["member"]).order_by(Trip.id)).all():
        booking = session.scalar(
            select(Booking).where(Booking.trip_id == trip.id, Booking.kind == sc["kind"], Booking.status == "ACTIVE"))
        if booking is not None:
            return _event(sc["type"], sc["member"], trip.id, booking.id, sc.get("delay_hours", 0),
                          sc.get("demand_spike", False), scenario_id)
    return None


DISRUPTIONS = {  # what can be fired at one specific booking of the member's own trip
    "FLIGHT": {"FLIGHT_CANCELLED", "MISSED_CONNECTION"},
    "TRAIN": {"TRAIN_CANCELLED"},
    "BUS": {"BUS_CANCELLED"},
    "HOTEL": {"HOTEL_OVERBOOKED"},
}


def build_booking_event(session: Session, booking_id: str, type_: str, delay_hours: float = 0,
                        demand_spike: bool = False) -> dict:
    b = session.get(Booking, booking_id)
    if b is None or b.status != "ACTIVE":
        raise ValueError("That booking is not active any more")
    if type_ not in DISRUPTIONS.get(b.kind, ()):
        raise ValueError(f"{type_.replace('_', ' ').title()} does not apply to a {b.kind.lower()}")
    trip = session.get(Trip, b.trip_id)
    return _event(type_, trip.member_id, trip.id, b.id, delay_hours, demand_spike, "own_booking")

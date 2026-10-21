"""Database tables. Flat on purpose so Tableau can read them without joins gymnastics."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Member(Base):
    __tablename__ = "members"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    home_city: Mapped[str] = mapped_column(String(60))
    budget_level: Mapped[str] = mapped_column(String(10))  # low | medium | high
    alert_channel: Mapped[str] = mapped_column(String(10))  # SMS | Email | Push
    consent_autorebook: Mapped[bool] = mapped_column(Boolean, default=True)
    consent_history: Mapped[bool] = mapped_column(Boolean, default=True)


class Trip(Base):
    __tablename__ = "trips"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    member_id: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(120))
    purpose_type: Mapped[str] = mapped_column(String(30))  # temple | business | monument
    purpose_place: Mapped[str] = mapped_column(String(80))
    destination_city: Mapped[str] = mapped_column(String(60))
    envelope: Mapped[float] = mapped_column(Float)  # original total budget
    pool_credit: Mapped[float] = mapped_column(Float, default=0.0)  # savings released so far


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    trip_id: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(10))  # FLIGHT | TRAIN | HOTEL | BUS
    payment_type: Mapped[str] = mapped_column(String(12))  # PREPAID | PAY_AFTER
    amount: Mapped[float] = mapped_column(Float)
    # What the very first booking cost. Ceilings are always derived from this, so a chain of
    # rebookings can never creep upward one step at a time.
    baseline_amount: Mapped[float] = mapped_column(Float)
    origin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(20), nullable=True)
    label: Mapped[str] = mapped_column(String(160))
    hotel_area: Mapped[str | None] = mapped_column(String(60), nullable=True)
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_per_night: Mapped[float | None] = mapped_column(Float, nullable=True)
    nights: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")  # ACTIVE | REBOOKED
    replaces_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BookingHistory(Base):
    """Past stays — this is what Tableau analyses to learn where a member likes to stay."""
    __tablename__ = "booking_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    member_id: Mapped[str] = mapped_column(String(20))
    city: Mapped[str] = mapped_column(String(60))
    purpose_type: Mapped[str] = mapped_column(String(30))
    purpose_place: Mapped[str] = mapped_column(String(80))
    hotel_name: Mapped[str] = mapped_column(String(120))
    hotel_area: Mapped[str] = mapped_column(String(60))
    distance_km: Mapped[float] = mapped_column(Float)
    price_per_night: Mapped[float] = mapped_column(Float)
    stayed_on: Mapped[str] = mapped_column(String(10))


class DisruptionEvent(Base):
    __tablename__ = "disruption_events"
    event_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    type: Mapped[str] = mapped_column(String(30))
    member_id: Mapped[str] = mapped_column(String(20))
    trip_id: Mapped[str] = mapped_column(String(20))
    booking_id: Mapped[str] = mapped_column(String(30))
    delay_hours: Mapped[float] = mapped_column(Float, default=0.0)
    demand_spike: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(20), default="simulator")
    detected_at: Mapped[datetime] = mapped_column(DateTime)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(40))
    member_id: Mapped[str] = mapped_column(String(20))
    trip_id: Mapped[str] = mapped_column(String(20))
    booking_id: Mapped[str] = mapped_column(String(30))
    event_type: Mapped[str] = mapped_column(String(30))
    # AUTO_BOOKED | NEEDS_APPROVAL | FALLBACK_OPTIONS | USER_APPROVED | USER_CHOSE | DECLINED
    status: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(10))
    payment_type: Mapped[str] = mapped_column(String(12))
    original_amount: Mapped[float] = mapped_column(Float)
    ceiling: Mapped[float] = mapped_column(Float)
    pool_credit_used: Mapped[float] = mapped_column(Float, default=0.0)
    chosen_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    chosen_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    chosen_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    options_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    notification: Mapped[str] = mapped_column(Text, default="")
    channel: Mapped[str] = mapped_column(String(10), default="Push")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

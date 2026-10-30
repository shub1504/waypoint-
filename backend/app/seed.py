"""Demo data: 3 card members, their trips, bookings and past stays."""
import random

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Booking, BookingHistory, Decision, DisruptionEvent, Member, Trip

MEMBERS = [
    dict(id="M001", name="Aarav Sharma", email="aarav@example.com", phone="+91-90000-00001",
         home_city="Delhi", budget_level="medium", alert_channel="Push"),
    dict(id="M002", name="Priya Mehta", email="priya@example.com", phone="+91-90000-00002",
         home_city="Delhi", budget_level="high", alert_channel="Email"),
    dict(id="M003", name="Rohan Verma", email="rohan@example.com", phone="+91-90000-00003",
         home_city="Delhi", budget_level="low", alert_channel="SMS"),
]

# (id, member, title, purpose_type, purpose_place, destination_city)
TRIPS = [
    ("T1", "M001", "Ujjain darshan", "temple", "Mahakaleshwar Temple", "Ujjain"),
    ("T2", "M002", "Mumbai client meetings", "business", "Bandra Kurla Complex", "Mumbai"),
    ("T3", "M003", "Jaipur weekend", "monument", "Amber Fort", "Jaipur"),
]


def _b(id, trip, kind, pay, amount, origin, dest, label, **kw):
    return Booking(id=id, trip_id=trip, kind=kind, payment_type=pay, amount=amount,
                   baseline_amount=amount, origin=origin, destination=dest, label=label, **kw)


def _bookings() -> list[Booking]:
    return [
        # Trip 1 — Aarav (envelope 10,000)
        _b("T1-FL", "T1", "FLIGHT", "PREPAID", 4200, "DEL", "IDR", "IndiGo 6E-2031 DEL→IDR"),
        _b("T1-HT", "T1", "HOTEL", "PAY_AFTER", 4000, None, None, "Hotel Ujjain Residency (2 nights)",
           hotel_area="Temple Area", distance_km=0.4, price_per_night=2000, nights=2),
        _b("T1-TR", "T1", "TRAIN", "PREPAID", 1800, "UJN", "NDLS", "Narmada Express 12912 UJN→NDLS"),
        # Trip 2 — Priya (envelope 23,500)
        _b("T2-FL", "T2", "FLIGHT", "PREPAID", 6500, "DEL", "BOM", "IndiGo 6E-6055 DEL→BOM"),
        _b("T2-HT", "T2", "HOTEL", "PAY_AFTER", 17000, None, None, "BKC Corporate Stay (2 nights)",
           hotel_area="BKC", distance_km=0.5, price_per_night=8500, nights=2),
        # Trip 3 — Rohan (envelope 5,000)
        _b("T3-FL", "T3", "FLIGHT", "PREPAID", 2200, "DEL", "JAI", "SpiceJet SG-8100 DEL→JAI"),
        _b("T3-HT", "T3", "HOTEL", "PAY_AFTER", 2800, None, None, "Amer Heritage Stay (2 nights)",
           hotel_area="Amer", distance_km=0.7, price_per_night=1400, nights=2),
    ]

# (member, purpose_type, purpose_place, hotel names, area, distance range, price range)
_HISTORY_PLANS = [
    ("M001", "temple", "Mahakaleshwar Temple", "Temple Area", (0.2, 0.7), (1700, 2600), 8),
    ("M001", "temple", "Kashi Vishwanath", "Temple Area", (0.3, 0.8), (1800, 2800), 4),
    ("M001", "business", "Connaught Place", "CP", (2.5, 4.0), (3500, 5000), 3),
    ("M002", "business", "Bandra Kurla Complex", "BKC", (0.3, 1.0), (8000, 12000), 9),
    ("M002", "leisure", "Juhu Beach", "Juhu", (0.2, 0.9), (7000, 9500), 3),
    ("M003", "monument", "Amber Fort", "Amer", (0.4, 1.4), (1100, 1800), 6),
    ("M003", "monument", "Red Fort", "Old Delhi", (0.8, 2.0), (1200, 1900), 4),
]


def _history() -> list[BookingHistory]:
    rng = random.Random(42)  # fixed seed -> same demo data every time
    rows = []
    for member, ptype, place, area, (d0, d1), (p0, p1), n in _HISTORY_PLANS:
        for i in range(n):
            rows.append(BookingHistory(
                member_id=member, city=place.split()[0], purpose_type=ptype, purpose_place=place,
                hotel_name=f"{area} Stay {i + 1}", hotel_area=area,
                distance_km=round(rng.uniform(d0, d1), 2),
                price_per_night=round(rng.uniform(p0, p1) / 50) * 50,
                stayed_on=f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
            ))
    return rows


def seed(session: Session, force: bool = False) -> bool:
    """Create demo data. Returns True if it seeded. `force` wipes and reseeds (demo reset)."""
    if session.scalar(select(Member.id).limit(1)) and not force:
        return False
    for table in (Decision, DisruptionEvent, Booking, Trip, BookingHistory, Member):
        session.execute(delete(table))
    session.add_all([Member(consent_autorebook=True, consent_history=True, **m) for m in MEMBERS])
    bookings = _bookings()
    envelopes = {}
    for b in bookings:
        envelopes[b.trip_id] = envelopes.get(b.trip_id, 0) + b.amount
    session.add_all([
        Trip(id=t, member_id=m, title=title, purpose_type=pt, purpose_place=pp,
             destination_city=city, envelope=envelopes[t], pool_credit=0.0)
        for t, m, title, pt, pp, city in TRIPS
    ])
    session.add_all(bookings)
    session.add_all(_history())
    session.flush()
    return True


def create_member(session: Session, name: str, email: str, phone: str, home_city: str,
                  budget_level: str, alert_channel: str) -> Member:
    """Sign up a new member with a starter trip (flight + hotel + train) and some past temple stays,
    so every demo scenario works for them straight away."""
    n = len(session.scalars(select(Member.id)).all()) + 1
    while session.get(Member, f"M{n:03d}") is not None:
        n += 1
    mid, tid = f"M{n:03d}", f"T{n}"
    m = Member(id=mid, name=name, email=email, phone=phone, home_city=home_city, budget_level=budget_level,
               alert_channel=alert_channel, consent_autorebook=True, consent_history=True)
    bookings = [
        _b(f"{tid}-FL", tid, "FLIGHT", "PREPAID", 4200, "DEL", "IDR", "IndiGo 6E-2031 DEL→IDR"),
        _b(f"{tid}-HT", tid, "HOTEL", "PAY_AFTER", 4000, None, None, "Hotel Ujjain Residency (2 nights)",
           hotel_area="Temple Area", distance_km=0.4, price_per_night=2000, nights=2),
        _b(f"{tid}-TR", tid, "TRAIN", "PREPAID", 1800, "UJN", "NDLS", "Narmada Express 12912 UJN→NDLS"),
    ]
    session.add(m)
    session.add(Trip(id=tid, member_id=mid, title="Ujjain darshan", purpose_type="temple",
                     purpose_place="Mahakaleshwar Temple", destination_city="Ujjain",
                     envelope=sum(b.amount for b in bookings), pool_credit=0.0))
    session.add_all(bookings)
    rng = random.Random(mid)
    for i in range(6):
        session.add(BookingHistory(
            member_id=mid, city="Mahakaleshwar", purpose_type="temple", purpose_place="Mahakaleshwar Temple",
            hotel_name=f"Temple Area Stay {i + 1}", hotel_area="Temple Area",
            distance_km=round(rng.uniform(0.2, 0.7), 2), price_per_night=round(rng.uniform(1700, 2600) / 50) * 50,
            stayed_on=f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"))
    session.flush()
    return m

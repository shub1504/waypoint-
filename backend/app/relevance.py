"""Relevance-Aware Rebooking (slide 7).

The deck uses Tableau to study where a member stayed on earlier trips. The same logic lives
here so the agent can use it in real time: from `booking_history` we learn the preferred
distance-to-purpose and preferred area, then score replacement hotels on both.
"""
import math
import statistics
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BookingHistory

MIN_RELEVANCE = 0.35  # below this a hotel defeats the point of the trip, however cheap


def learn_preference(
    session: Session, member_id: str, purpose_type: str, fallback_distance: float | None, fallback_area: str | None
) -> dict:
    rows = session.scalars(
        select(BookingHistory).where(
            BookingHistory.member_id == member_id, BookingHistory.purpose_type == purpose_type
        )
    ).all()
    if rows:
        dist = statistics.median(r.distance_km for r in rows)
        area = Counter(r.hotel_area for r in rows).most_common(1)[0][0]
        return {"pref_distance_km": round(dist, 2), "pref_area": area, "samples": len(rows), "source": "history"}
    return {
        "pref_distance_km": fallback_distance if fallback_distance is not None else 1.0,
        "pref_area": fallback_area,
        "samples": 0,
        "source": "original booking",
    }


def relevance_score(distance_km: float, area: str, pref: dict) -> float:
    """0..1. Full marks within ~25% of the preferred distance, fading smoothly after that."""
    allowed = max(pref["pref_distance_km"], 0.3) * 1.25
    over = max(0.0, distance_km - allowed)
    dist_score = math.exp(-over / 1.5)
    area_bonus = 1.0 if pref.get("pref_area") and area == pref["pref_area"] else 0.0
    return round(min(1.0, 0.8 * dist_score + 0.2 * area_bonus), 3)

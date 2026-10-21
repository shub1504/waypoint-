"""Spend Guardrail Engine + Trip Budget Pool (slides 5 and 6).

Pure functions, no database, no LLM. The guardrail must behave the same every time, so it is
plain arithmetic that can be unit-tested and explained to a card member.

ceiling      = original_amount * multiplier(payment_type, budget_level)
per-item cap = ceiling + pool_credit        (savings elsewhere can lift one leg)
trip cap     = trip_envelope * trip_cap(budget_level)   (whole trip can never run away)
"""
from dataclasses import asdict, dataclass

# Prepaid money is committed instantly, so the ceiling is tighter.
PREPAID_MULT = {"low": 1.3, "medium": 1.6, "high": 2.0}
# Pay-after items (hotel paid at checkout, cabs) are seen before paying, so more freedom.
PAY_AFTER_MULT = 2.5
# Hard stop on total trip spend as a multiple of the original envelope.
TRIP_CAP_MULT = {"low": 1.4, "medium": 1.7, "high": 2.2}


@dataclass
class Verdict:
    allowed: bool            # may the agent act on its own on this amount?
    amount: float
    ceiling: float           # base ceiling from original booking
    limit: float             # ceiling + pool credit actually available
    pool_used: float         # how much of the pool this amount needs
    trip_total_after: float
    trip_cap: float
    needs_consent: bool      # prepaid => member's standing consent is required
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


def ceiling_for(original: float, payment_type: str, level: str) -> float:
    mult = PAY_AFTER_MULT if payment_type == "PAY_AFTER" else PREPAID_MULT[level]
    return round(original * mult, 2)


def evaluate(
    amount: float,
    original: float,
    payment_type: str,
    level: str,
    pool_credit: float,
    committed_others: float,
    envelope: float,
    consent: bool = True,
) -> Verdict:
    base = ceiling_for(original, payment_type, level)
    limit = base + max(pool_credit, 0.0)
    pool_used = round(min(max(amount - base, 0.0), max(pool_credit, 0.0)), 2)
    trip_after = committed_others + amount
    trip_cap = round(envelope * TRIP_CAP_MULT[level], 2)
    needs_consent = payment_type == "PREPAID"

    if amount > limit:
        return Verdict(False, amount, base, limit, pool_used, trip_after, trip_cap, needs_consent,
                       f"₹{amount:,.0f} is above this item's limit of ₹{limit:,.0f}")
    if trip_after > trip_cap:
        return Verdict(False, amount, base, limit, pool_used, trip_after, trip_cap, needs_consent,
                       f"trip total would be ₹{trip_after:,.0f}, above the trip cap of ₹{trip_cap:,.0f}")
    if needs_consent and not consent:
        return Verdict(False, amount, base, limit, pool_used, trip_after, trip_cap, needs_consent,
                       "within limits, but prepaid booking needs your approval (auto-rebook is off)")
    how = "within the ceiling" if pool_used == 0 else f"within the ceiling using ₹{pool_used:,.0f} saved elsewhere on the trip"
    return Verdict(True, amount, base, limit, pool_used, trip_after, trip_cap, needs_consent,
                   f"₹{amount:,.0f} is {how} (limit ₹{limit:,.0f})")

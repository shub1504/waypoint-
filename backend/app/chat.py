"""Chat tab: answers a member's questions from their own data.

Plain keyword intents (English + Hinglish), no LLM, so every number in a reply comes straight from
the database and cannot be invented.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import guardrail
from app.models import Booking, Decision, Member, Trip

SUGGESTIONS = ["How much budget is left?", "What is my auto-rebook limit?", "Why did you pick that?", "Show my bookings"]

INTENTS = {
    "budget": ("budget", "spent", "left", "kitna", "bacha", "envelope", "pool", "paisa", "paise"),
    "limit": ("limit", "ceiling", "cap", "maximum"),
    "why": ("why", "kyun", "kyu", "reason", "explain", "samjha", "kaise"),
    "bookings": ("booking", "status", "trip", "kahan", "where", "flight", "hotel", "train", "ticket"),
    "settings": ("consent", "permission", "setting", "auto", "alert", "channel", "preference"),
}


def _inr(x: float) -> str:
    return f"₹{x:,.0f}"


def _intent(text: str) -> str:
    t = text.lower()
    for name, words in INTENTS.items():
        if any(w in t for w in words):
            return name
    return "help"


def reply(session: Session, member_id: str, text: str) -> dict:
    member = session.get(Member, member_id)
    if member is None:
        raise ValueError("Unknown member")
    trips = session.scalars(select(Trip).where(Trip.member_id == member_id)).all()
    active = session.scalars(
        select(Booking).where(Booking.trip_id.in_([t.id for t in trips] or [""]), Booking.status == "ACTIVE")
    ).all()
    first = member.name.split()[0]
    intent = _intent(text)

    if intent == "budget":
        lines = []
        for t in trips:
            spent = sum(b.amount for b in active if b.trip_id == t.id)
            pool = f", {_inr(t.pool_credit)} saved in your trip pool" if t.pool_credit else ""
            lines.append(f"{t.title}: {_inr(spent)} committed against an original budget of {_inr(t.envelope)}{pool}.")
        return dict(reply="\n".join(lines) or "You have no trips yet.", suggestions=SUGGESTIONS)

    if intent == "limit":
        lines = []
        for b in active:
            mult = guardrail.PAY_AFTER_MULT if b.payment_type == "PAY_AFTER" else guardrail.PREPAID_MULT[member.budget_level]
            lines.append(f"{b.label}: I can rebook up to {_inr(guardrail.ceiling_for(b.baseline_amount, b.payment_type, member.budget_level))} "
                         f"on my own ({_inr(b.baseline_amount)} × {mult}).")
        head = f"Your budget comfort is {member.budget_level}. Prepaid items get a tighter limit than pay-after items.\n"
        return dict(reply=head + "\n".join(lines), suggestions=SUGGESTIONS)

    if intent == "why":
        d = session.scalar(select(Decision).where(Decision.member_id == member_id).order_by(Decision.id.desc()))
        if d is None:
            return dict(reply="Nothing has been disrupted yet, so there is nothing to explain.", suggestions=SUGGESTIONS)
        return dict(reply=f"About '{d.chosen_label or d.kind.lower()}': {d.reasoning}", suggestions=SUGGESTIONS)

    if intent == "bookings":
        if not active:
            return dict(reply="You have no active bookings.", suggestions=SUGGESTIONS)
        lines = [f"{b.kind.title()}: {b.label}, {_inr(b.amount)} ({'prepaid' if b.payment_type == 'PREPAID' else 'pay at checkout'})"
                 for b in active]
        return dict(reply="Your active bookings:\n" + "\n".join(lines), suggestions=SUGGESTIONS)

    if intent == "settings":
        return dict(
            reply=(f"Auto-rebook is {'ON' if member.consent_autorebook else 'OFF'}, budget comfort is {member.budget_level}, "
                   f"alerts go by {member.alert_channel}. You can change these in Profile > Preferences."),
            suggestions=SUGGESTIONS)

    return dict(
        reply=(f"Hi {first}, I'm Waypoint. I watch your trips and step in when a flight, train or hotel is disrupted. "
               "Ask me about your budget, your limits, your bookings, or why I chose something."),
        suggestions=SUGGESTIONS)

"""Chat tab: answers a member's questions from their own data and live providers.

Plain keyword intents (English + Hinglish) and live search handling.
Every number in a database reply comes straight from the database and cannot be invented.
Live train and flight schedules are queried from live providers.
"""
import re
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, guardrail, live_providers
from app.models import Booking, Decision, Member, Trip

SUGGESTIONS = ["How much budget is left?", "What is my auto-rebook limit?", "Why did you pick that?", "Show my bookings"]

INTENTS = {
    "out_of_scope": ("poem", "poetry", "write code", "python", "javascript", "essay", "recipe", "math", "sing a song"),
    "planning": ("ghumne", "suggest", "kuch suggest", "koi bhi trip", "trip plan", "plan a trip", "itinerary", "vacation"),
    "budget": ("budget", "spent", "left", "kitna", "bacha", "envelope", "pool", "paisa", "paise"),
    "limit": ("limit", "ceiling", "cap", "maximum"),
    "why": ("why", "kyun", "kyu", "reason", "explain", "samjha", "kaise"),
    "bookings": ("my booking", "my bookings", "active booking", "show booking", "show my booking"),
    "settings": ("consent", "permission", "setting", "auto", "alert", "channel", "preference"),
    "train_status": ("is late", "late?", "running late", "running status", "train status"),
    "live_flight": ("flight", "airline", "fly", "flihgt", "plane"),
    "live_train": ("train", "railway", "gaadi", "gadi"),
}


def _inr(x: float) -> str:
    return f"₹{x:,.0f}"


def _detect_intent(text: str) -> str:
    t = text.lower()
    # Check 5-digit train number with late/status
    if re.search(r"\b\d{5}\b", t) and ("late" in t or "status" in t or "running" in t):
        return "train_status"

    for name, words in INTENTS.items():
        if any(w in t for w in words):
            return name

    # Travel movement like "go from ... to ..." or "... to ..." with city names
    if re.search(r"(?:go\s+)?from\s+[a-zA-Z\s]+\s+(?:to|se)\s+[a-zA-Z\s]+", t) or re.search(r"[a-zA-Z\s]+\s+(?:to|se)\s+[a-zA-Z\s]+", t):
        return "live_train"

    return "help"


def reply(session: Session, member_id: str, text: str, history: Optional[List[Dict[str, Any]]] = None) -> dict:
    member = session.get(Member, member_id)
    if member is None:
        raise ValueError("Unknown member")
    trips = session.scalars(select(Trip).where(Trip.member_id == member_id)).all()
    active = session.scalars(
        select(Booking).where(Booking.trip_id.in_([t.id for t in trips] or [""]), Booking.status == "ACTIVE")
    ).all()
    first = member.name.split()[0]
    intent = _detect_intent(text)

    if intent == "out_of_scope":
        return dict(
            reply="I am Waypoint, your travel disruption concierge. I can only assist with trips, trains, flights, hotels, and disruption rebooking.",
            suggestions=SUGGESTIONS,
            engine="rules",
        )

    if intent == "planning":
        return dict(
            reply=f"Hi {first}! Looking for a trip? Great budget destinations from your home city {member.home_city} include Jaipur, Agra, Ujjain (temples), and Goa. You can configure and save your new trip in Profile > New trip.",
            suggestions=SUGGESTIONS,
            engine="rules",
        )

    if intent == "train_status":
        m = re.search(r"\b\d{5}\b", text)
        train_num = m.group(0) if m else "12919"
        res = live_providers.train_live_status(train_num)
        if res.get("error"):
            return dict(
                reply=f"Train {train_num}: {res.get('error')}. You can track live running status directly on NTES/IRCTC.",
                suggestions=SUGGESTIONS,
                engine="live",
            )
        status = res.get("status", "running")
        delay_min = res.get("delay_min", 0)
        delay_text = "running on time" if delay_min == 0 else f"running late by {delay_min} min"
        station = res.get("current_station", "In transit")
        t_name = res.get("train_name") or f"Train {train_num}"

        rep = f"Train {train_num} ({t_name}) is {delay_text}. Currently near {station} (Status: {status})."
        return dict(reply=rep, suggestions=SUGGESTIONS, engine="live")

    if intent in ("live_train", "live_flight") or re.search(r"(?:from\s+)?[a-zA-Z\s]+\s+(?:to|se)\s+[a-zA-Z\s]+", text, re.IGNORECASE):
        entities = live_providers.extract_travel_entities(text)
        orig = entities.get("origin") or member.home_city
        dest = entities.get("destination") or ""
        date_iso = entities.get("date") or ""
        date_display = entities.get("date_display") or ""
        mode = entities.get("mode") or ("flight" if intent == "live_flight" else "train")

        if (not dest or not orig) and history:
            for prev in reversed(history[-4:]):
                prev_text = prev.get("text", "")
                prev_ent = live_providers.extract_travel_entities(prev_text)
                if not orig and prev_ent.get("origin"):
                    orig = prev_ent["origin"]
                if not dest and prev_ent.get("destination"):
                    dest = prev_ent["destination"]
                if prev_ent.get("mode") and mode == "train" and "flight" in prev_text.lower():
                    mode = "flight"

        if not dest:
            return dict(
                reply=f"Which city or station would you like to travel to from {orig.title()}?",
                suggestions=SUGGESTIONS,
                engine="live",
            )

        if orig and dest:
            date_label = f" on {date_display}" if date_display else ""

            if mode == "flight":
                res = live_providers.search_flights_live(orig, dest, date_iso)
                flights = res.get("flights", [])
                if flights:
                    total = len(flights)
                    sample = flights[:8]
                    count_hdr = f"showing 8 of {total} flights" if total > 8 else f"found {total} flight{'s' if total > 1 else ''}"
                    header = f"Flights from {orig.title()} to {dest.title()}{date_label} ({count_hdr}, soonest first):"
                    lines = []
                    for f in sample:
                        dep = f.get("departure_time", "N/A")
                        arr = f.get("arrival_time", "N/A")
                        price_part = f" - ₹{f['price']:,.0f}" if f.get("price") else ""
                        lines.append(f"• {f['name']}: departs {dep}, arrives {arr} ({f['duration']}, {f['stops_label']}){price_part}")
                    return dict(
                        reply=header + "\n" + "\n".join(lines),
                        suggestions=SUGGESTIONS,
                        engine="live",
                    )
                else:
                    err_msg = res.get("error") or f"No flights found from {orig.title()} to {dest.title()}{date_label}."
                    return dict(reply=err_msg, suggestions=SUGGESTIONS, engine="live")

            else:
                # Train search
                res = live_providers.search_trains_live(orig, dest, date_iso)
                trains = res.get("trains", [])
                if trains:
                    total = len(trains)
                    sample = trains[:8]
                    count_hdr = f"showing 8 of {total} trains" if total > 8 else f"found {total} train{'s' if total > 1 else ''}"
                    header = f"Trains from {orig.title()} to {dest.title()}{date_label} ({count_hdr}, soonest first):"
                    lines = [f"• {t['summary_line']}" for t in sample]
                    note = "\n\nNote: RailRadar provides live schedules and delays. Fares and seat availability must be verified on IRCTC."
                    return dict(
                        reply=header + "\n" + "\n".join(lines) + note,
                        suggestions=SUGGESTIONS,
                        engine="live",
                    )
                else:
                    if res.get("had_404"):
                        reply_msg = f"No trains found from {orig.title()} to {dest.title()}{date_label} on RailRadar. Please check alternative dates or verify directly on IRCTC."
                    elif res.get("error"):
                        reply_msg = f"Train search could not be completed ({res['error']}). Please check live train schedules directly on IRCTC."
                    else:
                        reply_msg = f"No trains found from {orig.title()} to {dest.title()}{date_label}. Please verify on IRCTC."
                    return dict(reply=reply_msg, suggestions=SUGGESTIONS, engine="live")

        return dict(
            reply=f"For live travel schedules, please mention origin and destination (e.g. 'trains from delhi to mumbai tomorrow' or 'mumbai se delhi flight friday').",
            suggestions=SUGGESTIONS,
            engine="live",
        )

    if intent == "budget":
        lines = []
        for t in trips:
            spent = sum(b.amount for b in active if b.trip_id == t.id)
            pool = f", {_inr(t.pool_credit)} saved in your trip pool" if t.pool_credit else ""
            lines.append(f"{t.title}: {_inr(spent)} committed against an original budget of {_inr(t.envelope)}{pool}.")
        return dict(reply="\n".join(lines) or "You have no trips yet.", suggestions=SUGGESTIONS, engine="rules")

    if intent == "limit":
        lines = []
        for b in active:
            mult = guardrail.PAY_AFTER_MULT if b.payment_type == "PAY_AFTER" else guardrail.PREPAID_MULT[member.budget_level]
            lines.append(f"{b.label}: I can rebook up to {_inr(guardrail.ceiling_for(b.baseline_amount, b.payment_type, member.budget_level))} "
                         f"on my own ({_inr(b.baseline_amount)} × {mult}).")
        head = f"Your budget comfort is {member.budget_level}. Prepaid items get a tighter limit than pay-after items.\n"
        return dict(reply=head + "\n".join(lines), suggestions=SUGGESTIONS, engine="rules")

    if intent == "why":
        d = session.scalar(select(Decision).where(Decision.member_id == member_id).order_by(Decision.id.desc()))
        if d is None:
            return dict(reply="Nothing has been disrupted yet, so there is nothing to explain.", suggestions=SUGGESTIONS, engine="rules")
        return dict(reply=f"About '{d.chosen_label or d.kind.lower()}': {d.reasoning}", suggestions=SUGGESTIONS, engine="rules")

    if intent == "bookings":
        if not active:
            return dict(reply="You have no active bookings.", suggestions=SUGGESTIONS, engine="rules")
        lines = [f"{b.kind.title()}: {b.label}, {_inr(b.amount)} ({'prepaid' if b.payment_type == 'PREPAID' else 'pay at checkout'})"
                 for b in active]
        return dict(reply="Your active bookings:\n" + "\n".join(lines), suggestions=SUGGESTIONS, engine="rules")

    if intent == "settings":
        return dict(
            reply=(f"Auto-rebook is {'ON' if member.consent_autorebook else 'OFF'}, budget comfort is {member.budget_level}, "
                   f"alerts go by {member.alert_channel}. You can change these in Profile > Preferences."),
            suggestions=SUGGESTIONS,
            engine="rules")

    return dict(
        reply=(f"Hi {first}, I'm Waypoint. I watch your trips and step in when a flight, train or hotel is disrupted. "
               "Ask me about live trains, live flights, your budget, your limits, your bookings, or why I chose something."),
        suggestions=SUGGESTIONS,
        engine="rules")

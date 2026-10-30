"""Chat tab brain: a Google ADK agent (Gemini) that talks to the member and calls Waypoint's own tools.

The model never decides money. It can only
  * READ: account, trips, limits, past decisions, alternatives (all computed by the guardrail engine), and
  * PROPOSE: a switch or a cancellation. A proposal is shown to the member as a card with a Confirm button;
    nothing is booked or cancelled until the member taps it (the same endpoints the rest of the app uses).

No GEMINI_API_KEY, or google-adk not installed, or any model error -> chat.py (keyword rules) answers instead.
"""
import json
import logging
import os

from sqlalchemy import select

from app import cancel, config, explore, guardrail
from app.db import session_scope
from app.models import Booking, Decision, Member, Trip

log = logging.getLogger("waypoint.chat")

APP_NAME = "waypoint"
_PENDING: dict[str, list[dict]] = {}  # member_id -> proposals made during the current turn


def _member_id(tool_context) -> str:
    return tool_context.state["member_id"]


def _inr(x: float) -> str:
    return f"₹{x:,.0f}"


def _mine(session, member_id: str):
    trips = session.scalars(select(Trip).where(Trip.member_id == member_id).order_by(Trip.id)).all()
    bookings = session.scalars(select(Booking).where(Booking.trip_id.in_([t.id for t in trips] or [""]))
                               .order_by(Booking.created_at, Booking.id)).all()
    return trips, bookings


# ------------------------------------------------------------------ read tools
def get_account(tool_context) -> dict:
    """The member's settings: name, budget comfort level, alert channel, consents and the spend-limit multipliers."""
    with session_scope() as s:
        m = s.get(Member, _member_id(tool_context))
        return dict(name=m.name, home_city=m.home_city, budget_level=m.budget_level, alert_channel=m.alert_channel,
                    auto_rebook_allowed=m.consent_autorebook, learns_from_history=m.consent_history,
                    prepaid_limit_multiplier=guardrail.PREPAID_MULT[m.budget_level],
                    pay_after_limit_multiplier=guardrail.PAY_AFTER_MULT)


def get_trips(tool_context) -> dict:
    """All of the member's trips with budget (committed vs original, saved trip pool) and every booking
    (id, kind, label, amount, auto_rebook_limit, status ACTIVE/REBOOKED/CANCELLED). Use the booking ids and trip ids from here
    for the other tools."""
    with session_scope() as s:
        trips, bookings = _mine(s, _member_id(tool_context))
        out = []
        for t in trips:
            bs = [b for b in bookings if b.trip_id == t.id]
            m = s.get(Member, t.member_id)
            lim = {b.id: explore.with_limit(explore.booking_dict(b), b, t, m).get("auto_limit") for b in bs}
            out.append(dict(
                trip_id=t.id, title=t.title, destination=t.destination_city, near=t.purpose_place,
                original_budget=t.envelope, committed_now=sum(b.amount for b in bs if b.status == "ACTIVE"),
                trip_pool_saved=t.pool_credit,
                bookings=[dict(booking_id=b.id, kind=b.kind, label=b.label, amount=b.amount, status=b.status,
                               payment="prepaid" if b.payment_type == "PREPAID" else "pay at checkout",
                               auto_rebook_limit=lim[b.id],
                               route=f"{b.origin}->{b.destination}" if b.origin else None) for b in bs]))
        return dict(trips=out)


def get_limit(booking_id: str, tool_context) -> dict:
    """What Waypoint may rebook an ACTIVE booking up to on its own (guardrail ceiling plus any trip pool credit)."""
    with session_scope() as s:
        b = s.get(Booking, booking_id)
        t = s.get(Trip, b.trip_id) if b else None
        if b is None or t.member_id != _member_id(tool_context):
            return dict(error="Unknown booking")
        m = s.get(Member, t.member_id)
        c = guardrail.ceiling_for(b.baseline_amount, b.payment_type, m.budget_level)
        return dict(booking=b.label, paid=b.amount, original_price=b.baseline_amount, auto_limit=c + t.pool_credit,
                    trip_pool_credit=t.pool_credit)


def recent_decisions(tool_context, count: int = 3) -> dict:
    """The latest things Waypoint did for this member (rebookings, swaps, cancellations) with its reasoning.
    Use it to answer 'why did you pick that?'."""
    with session_scope() as s:
        rows = s.scalars(select(Decision).where(Decision.member_id == _member_id(tool_context))
                         .order_by(Decision.id.desc()).limit(max(1, min(int(count), 10)))).all()
        return dict(decisions=[dict(what=d.event_type, status=d.status, chosen=d.chosen_label,
                                    amount=d.chosen_amount, limit=d.ceiling, reasoning=d.reasoning) for d in rows])


def cancellation_history(tool_context) -> dict:
    """Why this member cancelled things before, in their own words (the 'other' reasons and notes).
    Use it to be considerate, e.g. not suggesting what they already said did not suit them."""
    with session_scope() as s:
        rows = s.scalars(select(Decision).where(Decision.member_id == _member_id(tool_context),
                                                Decision.event_type == "USER_CANCEL").order_by(Decision.id.desc()).limit(10)).all()
        out = []
        for d in rows:
            info = json.loads(d.chosen_json) if d.chosen_json else {}
            out.append(dict(reason=info.get("reason_label"), their_words=info.get("note") or None, refund=d.chosen_label))
        return dict(cancellations=out)


def find_alternatives(booking_id: str, tool_context, max_results: int = 5) -> dict:
    """Other options for one ACTIVE booking (flight, train, bus, hotel), best first, each marked
    'within_limit' or not. Use for 'show me more options' or 'is there anything cheaper'."""
    with session_scope() as s:
        b = s.get(Booking, booking_id)
        t = s.get(Trip, b.trip_id) if b else None
        if b is None or t.member_id != _member_id(tool_context) or b.status != "ACTIVE":
            return dict(error="That booking is not active")
        p = explore.options_payload(s, booking_id)
        return dict(current=dict(label=b.label, amount=b.amount), auto_limit=p["limit"], options=[
            dict(label=o["label"], price=o["total_cost"], vs_current=o["delta"], within_limit=o["allowed"],
                 why=o["reason"], area=o["area"], km_from_place=o["distance_km"],
                 leaves_in_hours=o["depart_in_h"], journey_hours=o["duration_h"])
            for o in p["options"][:max(1, min(int(max_results), 8))]])


# ------------------------------------------------------------------ propose tools (need the member's tap)
def propose_switch(booking_id: str, option_label: str, tool_context) -> dict:
    """Propose replacing an ACTIVE booking with one option from find_alternatives (use its exact label).
    This does NOT book anything: the member sees a Confirm button. Tell them to tap it."""
    mid = _member_id(tool_context)
    with session_scope() as s:
        b = s.get(Booking, booking_id)
        t = s.get(Trip, b.trip_id) if b else None
        if b is None or t.member_id != mid or b.status != "ACTIVE":
            return dict(error="That booking is not active")
        _, _, _, opts = explore.build_options(s, booking_id)
        o = next((x for x in opts if x["label"] == option_label), None)
        if o is None:
            return dict(error="No option with that exact label. Call find_alternatives first.")
        v = o["verdict"]
        action = dict(type="switch", booking_id=booking_id, label=option_label, price=o["total_cost"],
                      title=f"Switch to {option_label}", detail=f"{_inr(o['total_cost'])} instead of {_inr(b.amount)}. {v['reason']}.",
                      confirm=f"Book {_inr(o['total_cost'])}", warn=not v["allowed"])
    _PENDING.setdefault(mid, []).append(action)
    return dict(proposed=True, price=action["price"], within_limit=not action["warn"], note=action["detail"])


def propose_cancel(trip_id: str, reason: str, tool_context, booking_id: str = "", note: str = "") -> dict:
    """Propose cancelling one booking (give booking_id) or the whole trip (leave booking_id empty).
    reason must be one of: plans_changed, medical, event_cancelled, better_option (better_option swaps ONE
    booking to a cheaper option and needs booking_id), other. Map the member's words to a reason. If their reason
    fits none of the first four, use "other" and put their reason in `note`, in their own words, a few words
    (required for "other"). If they gave no reason at all, ask for one short reason first.
    This does NOT cancel anything: the member sees a Confirm button. Tell them the expected refund."""
    mid = _member_id(tool_context)
    with session_scope() as s:
        t = s.get(Trip, trip_id)
        if t is None or t.member_id != mid:
            return dict(error="Unknown trip")
        try:
            p = cancel.plan(s, trip_id, booking_id or None, reason, note)
        except ValueError as e:
            return dict(error=str(e))
        if not p["ok"]:
            return dict(error=p["message"])
        action = dict(type="cancel", trip_id=trip_id, booking_id=booking_id or None, reason=reason, note=note,
                      title=("Cancel trip: " if not booking_id else "Cancel booking: ") + (t.title if not booking_id else p["items"][0]["label"]),
                      detail=p["message"], reason_label=p["reason_label"], items=p["items"],
                      confirm="Swap to cheaper option" if reason == "better_option" else "Confirm cancellation")
    _PENDING.setdefault(mid, []).append(action)
    return dict(proposed=True, reason=p["reason_label"], summary=p["message"], items=p["items"])


TOOLS = [get_account, get_trips, get_limit, recent_decisions, cancellation_history, find_alternatives, propose_switch, propose_cancel]

BASE_INSTRUCTION = """You are Waypoint, a travel-disruption concierge inside a card-member app.

Rules:
- Every fact and number must come from a tool result. Never guess prices, limits, refunds or booking ids.
  Call get_trips first when you need ids. Money and policy are decided by the tools, not by you.
- When you mention a booking, also say its auto-rebook limit (auto_rebook_limit) so the member knows how far
  Waypoint may go on its own, e.g. "limit ₹6,720 (₹4,200 x 1.6)".
- You cannot book or cancel. propose_switch and propose_cancel only show the member a Confirm button. After
  calling one, say what you proposed and that they need to tap Confirm. Never say it is already done.
- To cancel, you need a reason: plans_changed, medical, event_cancelled, better_option, or other (their own
  words in `note`). If they gave none, ask for one short reason. If it fits none of the named ones, use other.
- Creating a brand-new trip is done by the member in Profile > New trip (tickets, hotels, prices). If asked to
  "rebook" or "book" something that is not an existing booking, explain that and point them there; you can
  still show alternatives for bookings they already have.
- Reply in the language the member uses (English, Hindi or Hinglish). Be brief: 1 to 4 short sentences,
  plain text, amounts like ₹4,900. No markdown tables.
- Only travel topics. Politely decline anything else."""


def instruction(ctx) -> str:
    """Built fresh every turn so the agent always knows who it is talking to."""
    try:
        with session_scope() as s:
            m = s.get(Member, ctx.state["member_id"])
            if m is None:
                return BASE_INSTRUCTION
            mult = guardrail.PREPAID_MULT[m.budget_level]
            who = (f"\n\nThe member: {m.name}, budget comfort {m.budget_level} (prepaid limit {mult}x the original price, "
                   f"pay-at-checkout items {guardrail.PAY_AFTER_MULT}x), alerts by {m.alert_channel}, based in {m.home_city}. "
                   f"Auto-rebook is {'ON' if m.consent_autorebook else 'OFF: ask before anything prepaid'}. "
                   + ("A low budget means be extra careful about cost: lead with the cheapest option inside the limit. "
                      if m.budget_level == "low" else
                      "A high budget means comfort and closeness may matter more than the lowest price. " if m.budget_level == "high" else "")
                   + f"Address them as {m.name.split()[0]}.")
            return BASE_INSTRUCTION + who
    except Exception:
        return BASE_INSTRUCTION


def available() -> bool:
    if not config.GEMINI_API_KEY:
        return False
    try:
        import google.adk  # noqa: F401
        return True
    except Exception:  # not installed, or not supported on this Python yet
        return False


_runner = None


def _get_runner(model=None):
    global _runner
    if _runner is None or model is not None:
        from google.adk.agents import LlmAgent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        os.environ.setdefault("GOOGLE_API_KEY", config.GEMINI_API_KEY)
        agent = LlmAgent(name="waypoint_concierge", model=model or config.GEMINI_MODEL,
                         description="Waypoint travel-disruption concierge", instruction=instruction, tools=TOOLS)
        _runner = Runner(app_name=APP_NAME, agent=agent, session_service=InMemorySessionService())
    return _runner


def reset_sessions() -> None:
    """Forget all conversations (used by Reset demo data)."""
    global _runner
    _runner = None
    _PENDING.clear()


async def ask(member_id: str, text: str, model=None) -> dict:
    """One chat turn. Returns {reply, actions}. Raises if the model cannot be reached (caller falls back)."""
    from google.genai import types
    runner = _get_runner(model)
    svc = runner.session_service
    sid = f"chat-{member_id}"
    if await svc.get_session(app_name=APP_NAME, user_id=member_id, session_id=sid) is None:
        await svc.create_session(app_name=APP_NAME, user_id=member_id, session_id=sid, state={"member_id": member_id})
    _PENDING[member_id] = []
    reply = ""
    async for ev in runner.run_async(user_id=member_id, session_id=sid,
                                     new_message=types.Content(role="user", parts=[types.Part(text=text)])):
        if ev.is_final_response() and ev.content and ev.content.parts:
            reply = "".join(p.text or "" for p in ev.content.parts if getattr(p, "text", None)).strip() or reply
    return dict(reply=reply or "Sorry, I could not work that out. Could you rephrase?", actions=_PENDING.pop(member_id, []))

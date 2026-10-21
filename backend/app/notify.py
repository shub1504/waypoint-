"""Builds the message the member receives. Template first; Gemini (LangChain) optionally rewrites it.

The facts (what was booked, price, why) are fixed by the agent. The LLM may only rephrase them,
and any failure silently falls back to the template.
"""
import logging

from app import config

log = logging.getLogger("waypoint.notify")


def _template(member, trip, booking, d) -> str:
    first = member.name.split()[0]
    amt = f"₹{d.chosen_amount:,.0f}" if d.chosen_amount is not None else ""
    if d.status == "AUTO_BOOKED":
        return (f"Hi {first}, your {booking.kind.lower()} '{booking.label}' was disrupted. "
                f"We rebooked you on {d.chosen_label} for {amt}, within your spend limit. No action needed.")
    if d.status == "NEEDS_APPROVAL":
        return (f"Hi {first}, your {booking.kind.lower()} '{booking.label}' was disrupted. The best option "
                f"{d.chosen_label} costs {amt}, above your auto-rebook limit of ₹{d.ceiling:,.0f}. "
                f"Tap to approve or decline.")
    if d.status == "FALLBACK_OPTIONS":
        return (f"Hi {first}, no tickets are left from your original departure point for "
                f"'{booking.label}'. Choose: switch mode, or depart from a nearby station.")
    return f"Hi {first}, an update on your trip '{trip.title}'."


def compose(member, trip, booking, d) -> str:
    base = _template(member, trip, booking, d)
    if not config.GEMINI_API_KEY:
        return base
    try:  # optional: pip install langchain-google-genai
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(model=config.GEMINI_MODEL, google_api_key=config.GEMINI_API_KEY, temperature=0.3)
        out = llm.invoke(
            "Rewrite this travel alert as one calm, friendly SMS-length message. Keep every fact, "
            "rupee amount and name exactly as written. Do not add anything.\n\n" + base
        )
        text = (out.content if isinstance(out.content, str) else str(out.content)).strip()
        return text or base
    except Exception as e:  # never let the LLM block a rebooking
        log.warning("LLM rephrase skipped: %s", e)
        return base

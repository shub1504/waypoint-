"""The ADK chat agent, driven by a scripted fake model so no API key or network is needed.
What is proven: tools run against the real database, a proposal never changes data, and the member's
tap (the existing endpoints) is what actually cancels."""
import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

pytest.importorskip("google.adk")
from google.adk.models import BaseLlm  # noqa: E402
from google.adk.models.llm_response import LlmResponse  # noqa: E402
from google.genai import types  # noqa: E402

from app import cancel, chat_agent, db  # noqa: E402
from app.models import Base, Booking  # noqa: E402
from app.seed import seed  # noqa: E402


class ScriptedLlm(BaseLlm):
    """Calls get_trips, then propose_cancel on the first trip, then answers in text."""
    model: str = "scripted"

    async def generate_content_async(self, llm_request, stream=False):
        responses = [p.function_response for c in llm_request.contents for p in (c.parts or []) if p.function_response]
        if not responses:
            part = types.Part(function_call=types.FunctionCall(name="get_trips", args={}))
        elif len(responses) == 1:
            trip_id = responses[0].response["trips"][0]["trip_id"]
            part = types.Part(function_call=types.FunctionCall(
                name="propose_cancel", args={"trip_id": trip_id, "reason": "plans_changed"}))
        else:
            part = types.Part(text="I can cancel it. Tap Confirm to go ahead.")
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


@pytest.fixture()
def database(monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    SL = sessionmaker(bind=eng, expire_on_commit=False)
    monkeypatch.setattr(db, "SessionLocal", SL)
    with db.session_scope() as s:
        seed(s)
    chat_agent.reset_sessions()
    yield SL


def test_agent_proposes_but_does_not_cancel(database):
    out = asyncio.run(chat_agent.ask("M001", "cancel my trip, plans changed", model=ScriptedLlm()))
    assert "Confirm" in out["reply"]
    assert len(out["actions"]) == 1
    a = out["actions"][0]
    assert a["type"] == "cancel" and a["reason"] == "plans_changed" and a["trip_id"] == "T1"
    with db.session_scope() as s:  # nothing happened yet
        assert all(b.status == "ACTIVE" for b in s.query(Booking).filter_by(trip_id="T1"))


def test_member_tap_does_the_cancel(database):
    out = asyncio.run(chat_agent.ask("M001", "cancel my trip", model=ScriptedLlm()))
    a = out["actions"][0]
    with db.session_scope() as s:  # what the Confirm button calls
        d = cancel.apply(s, a["trip_id"], a["booking_id"], a["reason"], a["note"])
        assert d.status == "TRIP_CANCELLED"


def test_tools_cannot_touch_another_members_data(database):
    from types import SimpleNamespace
    ctx = SimpleNamespace(state={"member_id": "M002"})
    assert chat_agent.propose_cancel("T1", "plans_changed", ctx) == {"error": "Unknown trip"}
    assert chat_agent.find_alternatives("T1-FL", ctx)["error"]
    assert chat_agent.get_limit("T1-FL", ctx)["error"]


def test_other_reason_needs_words_and_is_remembered(database):
    from types import SimpleNamespace
    ctx = SimpleNamespace(state={"member_id": "M001"})
    with db.session_scope() as s:
        with pytest.raises(ValueError):
            cancel.plan(s, "T1", None, "other")  # no words, no cancel
    p = chat_agent.propose_cancel("T1", "other", ctx, note="boss moved the meeting")
    assert p["proposed"] is True
    a = chat_agent._PENDING["M001"][0]
    with db.session_scope() as s:
        cancel.apply(s, a["trip_id"], a["booking_id"], a["reason"], a["note"])
    hist = chat_agent.cancellation_history(ctx)["cancellations"]
    assert hist[0]["reason"] == "Something else" and hist[0]["their_words"] == "boss moved the meeting"


def test_instruction_knows_the_member_and_limits_are_listed(database):
    from types import SimpleNamespace
    text = chat_agent.instruction(SimpleNamespace(state={"member_id": "M003"}))
    assert "Rohan" in text and "low" in text and "1.3" in text
    t = chat_agent.get_trips(SimpleNamespace(state={"member_id": "M001"}))["trips"][0]
    fl = next(b for b in t["bookings"] if b["kind"] == "FLIGHT")
    assert fl["auto_rebook_limit"] == 4200 * 1.6

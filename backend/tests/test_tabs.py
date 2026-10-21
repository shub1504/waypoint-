"""Explore / Profile / Chat data on top of the same agent."""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import agent, chat, explore
from app.models import Base, Booking
from app.scenarios import build_event
from app.seed import seed


@pytest.fixture()
def s():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    sess = sessionmaker(bind=eng, expire_on_commit=False)()
    seed(sess)
    sess.commit()
    yield sess
    sess.close()


def run(s, scenario):
    d = agent.handle_event(s, build_event(s, scenario))
    s.commit()
    return d


def test_options_list_flags_guardrail(s):
    p = explore.options_payload(s, "T3-FL")  # Rohan, low budget, flight 2,200 -> limit 2,860
    assert p["ceiling"] == 2860
    assert p["options"] and all("allowed" in o for o in p["options"])
    assert all(not o["allowed"] for o in p["options"])  # both Jaipur flights are above 2,860
    assert p["options"][0]["delta"] == p["options"][0]["total_cost"] - 2200


def test_train_options_include_mode_switch_and_nearby(s):
    vias = {o["via"] for o in explore.options_payload(s, "T1-TR")["options"]}
    assert {"mode switch", "nearby departure"} <= vias


def test_hotel_options_sorted_allowed_first(s):
    opts = explore.options_payload(s, "T1-HT")["options"]
    flags = [o["allowed"] for o in opts]
    assert flags == sorted(flags, reverse=True)


def test_manual_switch_creates_booking_and_decision(s):
    p = explore.options_payload(s, "T1-FL")
    pick = next(o for o in p["options"] if o["allowed"])
    d = explore.switch(s, "T1-FL", pick["label"])
    s.commit()
    assert d.status == "USER_CHOSE" and d.event_type == "MANUAL_SWITCH"
    assert s.get(Booking, "T1-FL").status == "REBOOKED"


def test_manual_switch_above_limit_is_allowed_but_flagged(s):
    p = explore.options_payload(s, "T3-FL")
    d = explore.switch(s, "T3-FL", p["options"][0]["label"])
    assert "approved it yourself" in d.reasoning


def test_switch_unknown_label_fails(s):
    with pytest.raises(ValueError):
        explore.switch(s, "T1-FL", "No Such Flight")


def test_bookings_new_old_and_pairs(s):
    run(s, "flight_auto")
    b = explore.bookings_payload(s, "M001")
    assert any(x["original"] and x["original"]["id"] == "T1-FL" for x in b["new"])
    old = next(x for x in b["old"] if x["id"] == "T1-FL")
    assert old["replaced_by"] and old["decision"]["by"] == "Agent"
    assert len(b["past_stays"]) > 0


def test_chat_intents(s):
    assert "original budget" in chat.reply(s, "M001", "kitna budget bacha hai?")["reply"]
    assert "₹6,720" in chat.reply(s, "M001", "what is my limit")["reply"]
    assert "Nothing has been disrupted" in chat.reply(s, "M001", "why?")["reply"]
    run(s, "flight_auto")
    assert "within the ceiling" in chat.reply(s, "M001", "why did you pick that")["reply"]
    assert chat.reply(s, "M001", "hello")["suggestions"]


def test_new_member_gets_starter_trip_and_scenarios_run_on_them(s):
    from app.seed import create_member
    m = create_member(s, "Test User", "t@example.com", "+91-1", "Pune", "low", "Email")
    s.commit()
    assert m.id == "M004"
    ev = build_event(s, "flight_auto", member=m.id)
    assert ev["member_id"] == "M004" and ev["booking_id"].startswith("T4-")
    d = agent.handle_event(s, ev)
    assert d is not None and d.member_id == "M004"
    # a second account gets its own, non-clashing ids
    assert create_member(s, "Two", "2@example.com", "", "Delhi", "high", "SMS").id == "M005"


def _trip(s):
    from app import trips
    t = trips.create_trip(s, "M001", dict(
        title="Goa", destination="Goa", purpose_type="leisure", purpose_place="Calangute Beach",
        transports=[dict(kind="FLIGHT", origin="del", destination="goi", name="IndiGo 6E-301", price=6000)],
        hotels=[dict(name="Beach Breeze", area="Calangute", distance_km=0.8, nights=2, price_per_night=3000)]))
    s.commit()
    return t


def test_own_trip_gets_disrupted_and_rebooked(s):
    from app.scenarios import build_booking_event
    t = _trip(s)
    assert t.envelope == 12000
    fl = next(b for b in s.query(Booking).filter_by(trip_id=t.id) if b.kind == "FLIGHT")
    assert (fl.origin, fl.destination) == ("DEL", "GOI")
    d = agent.handle_event(s, build_booking_event(s, fl.id, "FLIGHT_CANCELLED"))
    assert d is not None and d.trip_id == t.id and d.options_json
    with pytest.raises(ValueError):
        build_booking_event(s, fl.id, "HOTEL_OVERBOOKED")  # wrong kind for this booking


def test_cancel_reason_changes_refund_and_status(s):
    from app import cancel
    t = _trip(s)
    plan_std = cancel.plan(s, t.id, None, "plans_changed")
    plan_med = cancel.plan(s, t.id, None, "medical")
    assert plan_std["total_refund"] == 4200 + 6000 and plan_med["total_refund"] == 12000  # 70% flight; hotel free
    d = cancel.apply(s, t.id, None, "medical", "family")
    assert d.status == "TRIP_CANCELLED" and "family" in d.reasoning
    assert all(b.status == "CANCELLED" for b in s.query(Booking).filter_by(trip_id=t.id))
    with pytest.raises(ValueError):
        cancel.apply(s, t.id, None, "plans_changed")  # nothing left to cancel

"""Run every deck scenario through the real agent on a throw-away in-memory database."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import agent, guardrail
from app.models import Base, Booking, Trip
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
    ev = build_event(s, scenario)
    assert ev is not None
    d = agent.handle_event(s, ev)
    s.commit()
    return d


# ---- guardrail maths -------------------------------------------------------
def test_ceiling_values():
    assert guardrail.ceiling_for(2000, "PREPAID", "medium") == 3200
    assert guardrail.ceiling_for(2000, "PREPAID", "low") == 2600
    assert guardrail.ceiling_for(2000, "PAY_AFTER", "medium") == 5000


def test_deck_example_5000_vs_2000_is_blocked():
    v = guardrail.evaluate(5000, 2000, "PREPAID", "medium", 0, 0, 2000)
    assert not v.allowed


def test_pool_lifts_limit():
    assert not guardrail.evaluate(3500, 2000, "PREPAID", "medium", 0, 0, 5000).allowed
    assert guardrail.evaluate(3500, 2000, "PREPAID", "medium", 400, 0, 5000).allowed


def test_trip_cap_blocks_even_within_item_limit():
    v = guardrail.evaluate(2500, 2000, "PREPAID", "low", 0, 9000, 5000)
    assert not v.allowed and "trip" in v.reason


# ---- scenarios --------------------------------------------------------------
def test_flight_auto_booked(s):
    d = run(s, "flight_auto")
    assert d.status == "AUTO_BOOKED"
    assert d.chosen_amount <= d.ceiling
    new = s.get(Booking, "T1-R4")
    assert new is not None and new.status == "ACTIVE" and new.baseline_amount == 4200
    assert s.get(Booking, "T1-FL").status == "REBOOKED"


def test_over_ceiling_needs_approval_then_approve(s):
    d = run(s, "over_ceiling")
    assert d.status == "NEEDS_APPROVAL"
    assert d.chosen_amount > d.ceiling
    assert s.get(Booking, "T3-FL").status == "ACTIVE"  # nothing was booked on its own
    agent.approve(s, d.id)
    s.commit()
    assert s.get(Booking, "T3-FL").status == "REBOOKED"


def test_pool_offset_auto_books_and_shrinks_hotel(s):
    d = run(s, "pool_offset")
    assert d.status == "AUTO_BOOKED"
    assert d.pool_credit_used > 0
    assert s.get(Booking, "T3-HT").nights == 1


def test_hotel_relevance_prefers_close_over_cheapest(s):
    d = run(s, "hotel_relevance")
    assert d.status == "AUTO_BOOKED"
    assert "Bus Stand" not in d.chosen_label  # cheapest hotel is 4.5 km from the temple
    new = [b for b in s.query(Booking).filter_by(trip_id="T1", status="ACTIVE", kind="HOTEL")][0]
    assert new.distance_km <= 0.6


def test_train_sold_out_gives_fallback_options(s):
    d = run(s, "train_sold_out")
    assert d.status == "FALLBACK_OPTIONS"
    import json
    opts = json.loads(d.options_json)
    assert any("bus" in o["label"].lower() for o in opts)
    assert any(o.get("extra_leg_cost") for o in opts)  # nearby-departure cost includes the cab leg
    agent.choose(s, d.id, 0)
    s.commit()
    assert s.get(Booking, "T1-TR").status == "REBOOKED"


def test_duplicate_event_is_ignored(s):
    ev = build_event(s, "flight_auto")
    assert agent.handle_event(s, ev) is not None
    s.commit()
    assert agent.handle_event(s, ev) is None


def test_chained_rebooking_keeps_original_baseline(s):
    run(s, "flight_auto")
    # second disruption on the same trip's (now rebooked) flight: ceiling must still derive from 4200
    d2 = run(s, "flight_auto")
    assert d2.original_amount == 4200


def test_missed_connection_high_budget(s):
    d = run(s, "missed_connection")
    assert d.status == "AUTO_BOOKED"

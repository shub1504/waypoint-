"""Test suite for Waypoint Journey feature (Start a Journey).

Checks:
1. Repeated searches produce identical results with realistic fare ordering.
2. Station code regex validation and stations endpoint.
3. Client-sent fare is ignored (server strictly recomputes from simulator).
4. Booking with no saved PayPal returns HTTP 400 and creates nothing in DB.
5. PayPal charge error rolls back completely (leaves 0 trips and 0 bookings).
6. Over-budget fare without confirmation returns HTTP 409, and succeeds with confirm_over_budget=True.
7. Duplicate booking guard: booking the same train twice returns HTTP 409 and only charges once.

Usage:
    python -m app.journey_test [search | tamper | no_paypal | pay_fail | budget | duplicate | all]
"""
import sys
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import delete, select

from app import journey, payments
from app.db import init_db, session_scope
from app.main import JourneyBookIn, book_journey, journey_stations, search_journey
from app.models import Booking, Member, Payment, Trip, VaultToken
from app.paypal_client import PayPalError


def _run(coro):
    """Run an async coroutine synchronously, avoiding Windows Python event loop IOCP delays."""
    stack = [coro]
    val = None
    while stack:
        try:
            res = stack[-1].send(val)
            if hasattr(res, "send"):
                stack.append(res)
                val = None
            else:
                val = res
        except StopIteration as e:
            stack.pop()
            val = e.value
    return val


def _cleanup_member(s, member_id: str):
    """Safely delete all test data created for a member."""
    trip_ids = s.scalars(select(Trip.id).where(Trip.member_id == member_id)).all()
    if trip_ids:
        b_ids = s.scalars(select(Booking.id).where(Booking.trip_id.in_(trip_ids))).all()
        if b_ids:
            s.execute(delete(Payment).where(Payment.booking_id.in_(b_ids)))
            s.execute(delete(Booking).where(Booking.id.in_(b_ids)))
        s.execute(delete(Trip).where(Trip.id.in_(trip_ids)))
    s.execute(delete(VaultToken).where(VaultToken.member_id == member_id))
    s.execute(delete(Member).where(Member.id == member_id))


def test_repeated_search():
    """Verify search is deterministic, outputs 3-5 trains, respects realistic fare hierarchy,

    validates station codes with regex ^[A-Z]{2,5}$, and tests GET /api/journey/stations.
    """
    print("--- 1. Testing Repeated Search, Hierarchy, Regex & Stations ---")
    orig, dest, date_str, budget = "NDLS", "UJN", "2026-11-20", 2000.0

    # 1. Test stations list endpoint
    stations = journey_stations()
    assert isinstance(stations, list) and len(stations) > 0, "Expected non-empty stations list"
    assert any(st["code"] == "NDLS" and st["name"] == "New Delhi" for st in stations)

    # 2. Test regex validation on station codes (after upper-casing)
    invalid_codes = ["N", "NDLSSS", "123", "ND-LS", "A", "ABCDEF"]
    for bad in invalid_codes:
        err = None
        try:
            search_journey(from_station=bad, to_station="UJN", date=date_str, budget=budget)
        except HTTPException as exc:
            err = exc
        assert err is not None and err.status_code == 400, f"Expected 400 for invalid station '{bad}'"

    # 3. Repeated search determinism
    res1 = search_journey(from_station=orig, to_station=dest, date=date_str, budget=budget)
    res2 = search_journey(from_station=orig, to_station=dest, date=date_str, budget=budget)
    assert res1 == res2, "Repeated search must return identical results"

    trains = res1["trains"]
    assert 3 <= len(trains) <= 5, f"Expected 3 to 5 trains, got {len(trains)}"

    # Check recommendations structure
    recs = res1.get("recommendations", {})
    for label in ("best_value", "fastest", "most_comfortable"):
        assert label in recs, f"Missing recommendation: {label}"
        assert recs[label]["reason"], f"Missing reason for recommendation: {label}"

    # Verify each train and class ordering
    for t in trains:
        assert t["train_no"] and t["name"] and t["departure"] and t["arrival"] and t["duration"]

        class_map = {c["cls"]: c for c in t["classes"]}
        assert set(class_map.keys()) == {"1A", "2A", "3A", "SL", "CC"}, "All 5 classes must be present"

        # Realistic fare order: SL < 3A < 2A < 1A, with CC between SL and 2A
        sl = class_map["SL"]["fare"]
        cc = class_map["CC"]["fare"]
        a3 = class_map["3A"]["fare"]
        a2 = class_map["2A"]["fare"]
        a1 = class_map["1A"]["fare"]

        assert sl < a3 < a2 < a1, f"Expected SL < 3A < 2A < 1A, got SL={sl}, 3A={a3}, 2A={a2}, 1A={a1}"
        assert sl < cc < a2, f"Expected CC between SL and 2A, got SL={sl}, CC={cc}, 2A={a2}"

        # Verdict check
        for c in t["classes"]:
            if c["fare"] <= budget:
                assert c["verdict"] == "within budget" and c["within_budget"] is True
            else:
                assert c["verdict"] == "over budget, needs your approval" and c["within_budget"] is False

    # Fastest badge class check: must be an available (non-WL) class
    fastest_train = min(trains, key=lambda tr: tr["duration_minutes"])
    fastest_cls_match = [c for c in fastest_train["classes"] if c.get("badge") == "Fastest"]
    assert len(fastest_cls_match) > 0, "Fastest train must have a class badged as Fastest"
    assert not fastest_cls_match[0]["availability"].startswith("WL"), "Fastest badge class must NOT be waitlisted"

    print(f"[PASS] Search: stations endpoint verified, regex validated, 2 identical queries ({len(trains)} trains), SL < CC < 3A < 2A < 1A verified.")


def test_tampered_fare_ignored():
    """Verify that any client-sent fare is ignored and the server recomputes the true fare."""
    print("--- 2. Testing Client-Sent Fare Ignored ---")
    orig, dest, date_str = "NDLS", "UJN", "2026-11-20"

    trains = journey.simulate_trains(orig, dest, date_str)
    target_train = trains[0]
    target_cls = next(c for c in target_train["classes"] if c["available"] and not c["availability"].startswith("WL"))
    real_fare = float(target_cls["fare"])

    member_id = "M_TEST_TAMPER"
    with session_scope() as s:
        _cleanup_member(s, member_id)
        s.add(Member(id=member_id, name="Test Member", email="tamper@example.com",
                     phone="+91-99999-00001", home_city="Delhi", budget_level="high",
                     alert_channel="Email"))
        s.add(VaultToken(member_id=member_id, vault_id="vault_dummy_123", active=True))

    def mock_charge_saved(session, booking_id):
        b = session.get(Booking, booking_id)
        tr = session.get(Trip, b.trip_id)
        p = Payment(booking_id=b.id, trip_id=b.trip_id, member_id=tr.member_id,
                    request_key="test-key", amount_inr=b.amount, amount_usd=round(b.amount / 85.0, 2),
                    status="CAPTURED", order_id="ORDER-TEST-123", capture_id="CAP-TEST-123")
        session.add(p)
        session.flush()
        return p

    try:
        payload_data = {
            "member_id": member_id,
            "train_no": target_train["train_no"],
            "cls": target_cls["cls"],
            "date": date_str,
            "from": orig,
            "to": dest,
            "budget": real_fare + 500.0,
            "confirm_over_budget": False,
            "fare": 1.0,      # Tampered!
            "amount": 1.0,    # Tampered!
            "price": 1.0,     # Tampered!
        }
        body = JourneyBookIn(**payload_data)

        with patch.object(payments, "charge_saved", side_effect=mock_charge_saved):
            result = _run(book_journey(body))

        trip_id = result["trip_id"]
        with session_scope() as s:
            bk = s.scalar(select(Booking).where(Booking.trip_id == trip_id))
            tr = s.get(Trip, trip_id)

            assert bk.amount == real_fare, f"Expected booking amount {real_fare}, got {bk.amount}"
            assert bk.baseline_amount == real_fare, f"Expected baseline_amount {real_fare}, got {bk.baseline_amount}"
            assert tr.envelope == real_fare, f"Expected trip envelope {real_fare}, got {tr.envelope}"
            # Check title and label format
            orig_name = journey.STATION_NAMES.get(orig, orig)
            dest_name = journey.STATION_NAMES.get(dest, dest)
            assert tr.title == f"{orig_name} to {dest_name} on {date_str}"
            assert f"{target_train['name']} ({target_cls['cls']}) {date_str}" in bk.label

        print(f"[PASS] Client-sent fare ignored: client sent INR 1.00, server charged simulated INR {real_fare:,.0f}.")
    finally:
        with session_scope() as s:
            _cleanup_member(s, member_id)


def test_no_paypal_error():
    """Verify that booking with no saved PayPal returns HTTP 400 and creates no Trip/Booking."""
    print("--- 3. Testing No-PayPal Error & Rollback ---")
    orig, dest, date_str = "NDLS", "UJN", "2026-11-20"

    trains = journey.simulate_trains(orig, dest, date_str)
    target_train = trains[0]
    target_cls = next(c for c in target_train["classes"] if not c["availability"].startswith("WL"))

    member_id = "M_TEST_NO_PAYPAL"
    with session_scope() as s:
        _cleanup_member(s, member_id)
        s.add(Member(id=member_id, name="No PayPal User", email="nopaypal@example.com",
                     phone="+91-99999-00002", home_city="Delhi", budget_level="low",
                     alert_channel="SMS"))

    try:
        body = JourneyBookIn(
            member_id=member_id,
            train_no=target_train["train_no"],
            cls=target_cls["cls"],
            date=date_str,
            from_station=orig,
            to_station=dest,
            budget=5000.0,
            confirm_over_budget=False,
        )

        error_caught = None
        try:
            _run(book_journey(body))
        except HTTPException as exc:
            error_caught = exc

        assert error_caught is not None, "Expected HTTPException when member has no saved PayPal"
        assert error_caught.status_code == 400, f"Expected HTTP 400, got {error_caught.status_code}"
        assert "PayPal" in error_caught.detail, f"Expected PayPal mention in detail, got: {error_caught.detail}"

        with session_scope() as s:
            trip_count = len(s.scalars(select(Trip).where(Trip.member_id == member_id)).all())
            assert trip_count == 0, f"Expected 0 trips created, found {trip_count}"

        print(f"[PASS] No-PayPal check: rejected with HTTP 400 ('{error_caught.detail}') and 0 records created.")
    finally:
        with session_scope() as s:
            _cleanup_member(s, member_id)


def test_paypal_charge_failure_rollback():
    """Verify that charge_saved raising PayPalError returns HTTP 400 and leaves 0 trips and 0 bookings."""
    print("--- 4. Testing PayPal Charge Failure Rollback ---")
    orig, dest, date_str = "NDLS", "UJN", "2026-11-20"

    trains = journey.simulate_trains(orig, dest, date_str)
    target_train = trains[0]
    target_cls = next(c for c in target_train["classes"] if c["available"] and not c["availability"].startswith("WL"))

    member_id = "M_TEST_PAY_FAIL"
    with session_scope() as s:
        _cleanup_member(s, member_id)
        s.add(Member(id=member_id, name="Pay Fail User", email="payfail@example.com",
                     phone="+91-99999-00003", home_city="Delhi", budget_level="medium",
                     alert_channel="Push"))
        s.add(VaultToken(member_id=member_id, vault_id="vault_dummy_fail", active=True))

    def mock_charge_fail(session, booking_id):
        raise PayPalError("Card declined in sandbox")

    try:
        body = JourneyBookIn(
            member_id=member_id,
            train_no=target_train["train_no"],
            cls=target_cls["cls"],
            date=date_str,
            from_station=orig,
            to_station=dest,
            budget=5000.0,
            confirm_over_budget=False,
        )

        error_caught = None
        with patch.object(payments, "charge_saved", side_effect=mock_charge_fail):
            try:
                _run(book_journey(body))
            except HTTPException as exc:
                error_caught = exc

        assert error_caught is not None, "Expected HTTPException when PayPal payment fails"
        assert error_caught.status_code == 400, f"Expected HTTP 400, got {error_caught.status_code}"

        # Verify database has zero trips and zero bookings
        with session_scope() as s:
            trips = s.scalars(select(Trip).where(Trip.member_id == member_id)).all()
            bookings = s.scalars(select(Booking).join(Trip, Trip.id == Booking.trip_id).where(Trip.member_id == member_id)).all()
            assert len(trips) == 0, f"Expected 0 trips after rollback, got {len(trips)}"
            assert len(bookings) == 0, f"Expected 0 bookings after rollback, got {len(bookings)}"

        print(f"[PASS] PayPal charge failure: rejected with HTTP 400 ('{error_caught.detail}') and 0 records remain.")
    finally:
        with session_scope() as s:
            _cleanup_member(s, member_id)


def test_over_budget_confirmation():
    """Verify that over-budget fare without confirm_over_budget returns HTTP 409 and creates nothing,

    and with confirm_over_budget=True succeeds.
    """
    print("--- 5. Testing Over-Budget Confirmation Guard ---")
    orig, dest, date_str = "NDLS", "UJN", "2026-11-20"

    trains = journey.simulate_trains(orig, dest, date_str)
    target_train = trains[0]
    target_cls = next(c for c in target_train["classes"] if c["available"] and not c["availability"].startswith("WL"))
    real_fare = float(target_cls["fare"])

    member_id = "M_TEST_OVER_BUDGET"
    with session_scope() as s:
        _cleanup_member(s, member_id)
        s.add(Member(id=member_id, name="Budget User", email="budget@example.com",
                     phone="+91-99999-00004", home_city="Delhi", budget_level="low",
                     alert_channel="Email"))
        s.add(VaultToken(member_id=member_id, vault_id="vault_dummy_bgt", active=True))

    def mock_charge_saved(session, booking_id):
        b = session.get(Booking, booking_id)
        tr = session.get(Trip, b.trip_id)
        p = Payment(booking_id=b.id, trip_id=b.trip_id, member_id=tr.member_id,
                    request_key="test-key-bgt", amount_inr=b.amount, amount_usd=round(b.amount / 85.0, 2),
                    status="CAPTURED", order_id="ORDER-BGT", capture_id="CAP-BGT")
        session.add(p)
        session.flush()
        return p

    try:
        # User budget is intentionally set below the actual fare
        tight_budget = max(100.0, real_fare - 200.0)

        # Step 1: Without confirm_over_budget -> must return 409
        body_unconfirmed = JourneyBookIn(
            member_id=member_id,
            train_no=target_train["train_no"],
            cls=target_cls["cls"],
            date=date_str,
            from_station=orig,
            to_station=dest,
            budget=tight_budget,
            confirm_over_budget=False,
        )

        err_409 = None
        try:
            _run(book_journey(body_unconfirmed))
        except HTTPException as exc:
            err_409 = exc

        assert err_409 is not None, "Expected HTTPException 409 for unconfirmed over-budget booking"
        assert err_409.status_code == 409, f"Expected 409, got {err_409.status_code}"
        assert err_409.detail == "This fare is over your budget. Please confirm to continue."

        with session_scope() as s:
            trips = s.scalars(select(Trip).where(Trip.member_id == member_id)).all()
            assert len(trips) == 0, f"Expected 0 trips created on 409, got {len(trips)}"

        # Step 2: With confirm_over_budget=True -> must succeed
        body_confirmed = JourneyBookIn(
            member_id=member_id,
            train_no=target_train["train_no"],
            cls=target_cls["cls"],
            date=date_str,
            from_station=orig,
            to_station=dest,
            budget=tight_budget,
            confirm_over_budget=True,
        )

        with patch.object(payments, "charge_saved", side_effect=mock_charge_saved):
            res = _run(book_journey(body_confirmed))

        assert res.get("ok") is True, "Expected successful booking when confirmed"
        with session_scope() as s:
            trip_count = len(s.scalars(select(Trip).where(Trip.member_id == member_id)).all())
            assert trip_count == 1, f"Expected 1 trip created when confirmed, got {trip_count}"

        print(f"[PASS] Over-budget guard: unconfirmed returned HTTP 409 with 0 records; confirmed succeeded.")
    finally:
        with session_scope() as s:
            _cleanup_member(s, member_id)


def test_duplicate_booking_guard():
    """Verify that booking the same train twice returns HTTP 409 and only one charge happens."""
    print("--- 6. Testing Duplicate Booking Guard ---")
    orig, dest, date_str = "NDLS", "UJN", "2026-11-20"

    trains = journey.simulate_trains(orig, dest, date_str)
    target_train = trains[0]
    target_cls = next(c for c in target_train["classes"] if c["available"] and not c["availability"].startswith("WL"))
    real_fare = float(target_cls["fare"])

    member_id = "M_TEST_DUP"
    with session_scope() as s:
        _cleanup_member(s, member_id)
        s.add(Member(id=member_id, name="Dup User", email="dup@example.com",
                     phone="+91-99999-00005", home_city="Delhi", budget_level="high",
                     alert_channel="Push"))
        s.add(VaultToken(member_id=member_id, vault_id="vault_dummy_dup", active=True))

    charge_count = [0]

    def mock_charge_saved(session, booking_id):
        charge_count[0] += 1
        b = session.get(Booking, booking_id)
        tr = session.get(Trip, b.trip_id)
        p = Payment(booking_id=b.id, trip_id=b.trip_id, member_id=tr.member_id,
                    request_key=f"test-key-dup-{charge_count[0]}", amount_inr=b.amount,
                    amount_usd=round(b.amount / 85.0, 2), status="CAPTURED",
                    order_id=f"ORDER-DUP-{charge_count[0]}", capture_id=f"CAP-DUP-{charge_count[0]}")
        session.add(p)
        session.flush()
        return p

    try:
        body = JourneyBookIn(
            member_id=member_id,
            train_no=target_train["train_no"],
            cls=target_cls["cls"],
            date=date_str,
            from_station=orig,
            to_station=dest,
            budget=real_fare + 500.0,
            confirm_over_budget=False,
        )

        # 1st booking -> must succeed
        with patch.object(payments, "charge_saved", side_effect=mock_charge_saved):
            res1 = _run(book_journey(body))
        assert res1.get("ok") is True, "First booking should succeed"
        assert charge_count[0] == 1, f"Expected 1 charge, got {charge_count[0]}"

        # 2nd booking -> must raise 409 "You already booked this train"
        err_dup = None
        with patch.object(payments, "charge_saved", side_effect=mock_charge_saved):
            try:
                _run(book_journey(body))
            except HTTPException as exc:
                err_dup = exc

        assert err_dup is not None, "Expected HTTPException 409 on duplicate booking"
        assert err_dup.status_code == 409, f"Expected 409, got {err_dup.status_code}"
        assert err_dup.detail == "You already booked this train", f"Unexpected detail: {err_dup.detail}"
        assert charge_count[0] == 1, f"Expected charge count to remain 1, got {charge_count[0]}"

        print(f"[PASS] Duplicate guard: 2nd booking returned HTTP 409 ('{err_dup.detail}') and charged only once.")
    finally:
        with session_scope() as s:
            _cleanup_member(s, member_id)


def main():
    init_db()
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else "all"

    if arg in ("search", "all"):
        test_repeated_search()
    if arg in ("tamper", "all"):
        test_tampered_fare_ignored()
    if arg in ("no_paypal", "all"):
        test_no_paypal_error()
    if arg in ("pay_fail", "all"):
        test_paypal_charge_failure_rollback()
    if arg in ("budget", "all"):
        test_over_budget_confirmation()
    if arg in ("duplicate", "all"):
        test_duplicate_booking_guard()

    if arg not in ("search", "tamper", "no_paypal", "pay_fail", "budget", "duplicate", "all"):
        print("Usage: python -m app.journey_test [search | tamper | no_paypal | pay_fail | budget | duplicate | all]")
        sys.exit(1)

    print("\n==========================================")
    print("ALL PHASE 1 REVIEW CHECKS PASSED!")
    print("==========================================")


if __name__ == "__main__":
    main()

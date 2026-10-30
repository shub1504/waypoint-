import sys

from sqlalchemy import select

from app import payments
from app.db import init_db, session_scope
from app.models import Booking

USAGE = "Usage: python -m app.pay_flow_test start | authorize PAYMENT_ID | capture PAYMENT_ID"
if len(sys.argv) < 2:
    sys.exit(USAGE)

init_db()  # makes sure the new payments table exists
with session_scope() as s:
    if sys.argv[1] == "start":
        b = s.scalar(select(Booking).where(Booking.status == "ACTIVE", Booking.payment_type == "PREPAID"))
        if b is None:
            sys.exit("No active prepaid booking found")
        p = payments.start_payment(s, b.id)
        print(f"Booking: {b.label} (INR {b.amount:,.0f})")
        print(f"Payment ID: {p.id} | USD {p.amount_usd:.2f} | status {p.status}")
        print("Approve link:", p.approve_url)
    elif sys.argv[1] == "authorize" and len(sys.argv) == 3:
        p = payments.authorize(s, int(sys.argv[2]))
        print("Status:", p.status, "| Authorization:", p.authorization_id)
    elif sys.argv[1] == "capture" and len(sys.argv) == 3:
        p = payments.capture(s, int(sys.argv[2]))
        print("Status:", p.status, "| Capture:", p.capture_id)
    elif sys.argv[1] == "autocharge" and len(sys.argv) == 3:
        p = payments.charge_saved(s, sys.argv[2])
        print("Status:", p.status, "| USD", f"{p.amount_usd:.2f}", "| Capture:", p.capture_id)
    else:
        sys.exit(USAGE)
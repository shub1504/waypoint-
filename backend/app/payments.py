"""Bridge between Waypoint bookings and PayPal.

Rules that never bend:
- the amount is read from the booking row, never from a request
- a booking can have only one live payment (no double charge)
- after authorizing, the amount PayPal holds must equal the amount we asked for
"""
import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, paypal_client
from app.models import Booking, Member, Payment, PaymentRefund, Trip, VaultSetup, VaultToken, utcnow
from app.paypal_client import PayPalError

LIVE = ("CREATED", "AUTHORIZED", "CAPTURED")


def inr_to_usd(amount_inr: float) -> Decimal:
    usd = (Decimal(str(amount_inr)) / Decimal(str(config.DEMO_INR_PER_USD))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP)
    return max(usd, Decimal("0.01"))


def start_payment(session: Session, booking_id: str) -> Payment:
    """Create the PayPal order for a prepaid booking. The member still has to approve it."""
    booking = session.get(Booking, booking_id)
    if booking is None or booking.status != "ACTIVE":
        raise PayPalError("Booking is not active")
    if booking.payment_type != "PREPAID":
        raise PayPalError("Only prepaid bookings are paid through PayPal")

    existing = session.scalar(select(Payment).where(
        Payment.booking_id == booking.id, Payment.status.in_(LIVE)))
    if existing:
        return existing

    from app.models import Trip
    trip = session.get(Trip, booking.trip_id)
    usd = inr_to_usd(booking.amount)
    key = uuid.uuid4().hex
    order = paypal_client.create_order(usd, description=booking.label, request_id=key,
                                       intent="AUTHORIZE")
    link = next((l["href"] for l in order.get("links", [])
                 if l["rel"] in ("approve", "payer-action")), None)
    p = Payment(booking_id=booking.id, trip_id=booking.trip_id, member_id=trip.member_id,
                request_key=key, amount_inr=booking.amount, amount_usd=float(usd),
                status="CREATED", order_id=order["id"], approve_url=link)
    session.add(p)
    session.flush()
    return p


def authorize(session: Session, payment_id: int) -> Payment:
    """After the member approved on PayPal: place the hold, and verify the held amount."""
    p = session.get(Payment, payment_id)
    if p is None or p.status != "CREATED":
        raise PayPalError("Payment is not waiting for authorization")
    result = paypal_client.authorize_order(p.order_id, request_id=p.request_key + "-auth")
    auth = result["purchase_units"][0]["payments"]["authorizations"][0]
    held = Decimal(auth["amount"]["value"])
    if held != Decimal(str(p.amount_usd)).quantize(Decimal("0.01")):
        paypal_client.void_authorization(auth["id"])
        p.status, p.updated_at = "VOIDED", utcnow()
        raise PayPalError("Held amount did not match the booking; hold released")
    p.authorization_id, p.status, p.updated_at = auth["id"], "AUTHORIZED", utcnow()
    return p


def capture(session: Session, payment_id: int) -> Payment:
    """Booking confirmed: take the held money."""
    p = session.get(Payment, payment_id)
    if p is None or p.status != "AUTHORIZED":
        raise PayPalError("Payment is not authorized")
    result = paypal_client.capture_authorization(p.authorization_id, request_id=p.request_key + "-cap")
    p.capture_id, p.status, p.updated_at = result["id"], "CAPTURED", utcnow()
    return p

def settle_cancellation(session: Session, booking_id: str, refund_inr: float) -> dict | None:
    """A booking was cancelled: give back whatever PayPal holds for it. None = no payment existed."""
    p = session.scalar(select(Payment).where(
        Payment.booking_id == booking_id, Payment.status.in_(LIVE)).order_by(Payment.id.desc()))
    if p is None:
        return None

    if p.status == "CREATED":
        p.status, p.updated_at = "VOIDED", utcnow()
        return dict(kind="NONE", usd=0.0, status="VOIDED",
                    note="PayPal checkout was never completed, so nothing was charged.")

    if p.status == "AUTHORIZED":
        paypal_client.void_authorization(p.authorization_id, request_id=p.request_key + "-void")
        p.status, p.updated_at = "VOIDED", utcnow()
        session.add(PaymentRefund(payment_id=p.id, booking_id=booking_id, kind="VOID",
                                  amount_inr=p.amount_inr, amount_usd=p.amount_usd,
                                  paypal_id=p.authorization_id, status="COMPLETED"))
        return dict(kind="VOID", usd=p.amount_usd, status="VOIDED",
                    note=f"the ${p.amount_usd:.2f} hold on PayPal was released, nothing was charged.")

    # CAPTURED: refund exactly what the cancellation rules say, never more than was paid
    paid_usd = Decimal(str(p.amount_usd)).quantize(Decimal("0.01"))
    refund_inr = min(max(float(refund_inr), 0.0), p.amount_inr)
    if refund_inr <= 0:
        return dict(kind="NONE", usd=0.0, status=p.status,
                    note="no refund is due under the cancellation rules, so PayPal was not changed.")
    usd = paid_usd if refund_inr >= p.amount_inr - 0.005 else min(inr_to_usd(refund_inr), paid_usd)
    result = paypal_client.refund_capture(p.capture_id, usd, note="Waypoint cancellation",
                                          request_id=p.request_key + "-refund")
    p.status, p.updated_at = "REFUNDED", utcnow()
    session.add(PaymentRefund(payment_id=p.id, booking_id=booking_id, kind="REFUND",
                              amount_inr=refund_inr, amount_usd=float(usd),
                              paypal_id=result["id"], status=result.get("status", "COMPLETED")))
    return dict(kind="REFUND", usd=float(usd), status=result.get("status", "COMPLETED"),
                note=f"${usd} refunded to your PayPal (₹{refund_inr:,.0f} at the demo rate).")
   
def charge_saved(session: Session, booking_id: str) -> Payment:
    """Charge a prepaid booking to the member's saved PayPal. The amount comes from the booking row only."""
    booking = session.get(Booking, booking_id)
    if booking is None or booking.status != "ACTIVE":
        raise PayPalError("Booking is not active")
    if booking.payment_type != "PREPAID":
        raise PayPalError("Only prepaid bookings are paid through PayPal")

    existing = session.scalar(select(Payment).where(
        Payment.booking_id == booking.id, Payment.status.in_(LIVE)))
    if existing:
        return existing

    trip = session.get(Trip, booking.trip_id)
    token = session.scalar(select(VaultToken).where(
        VaultToken.member_id == trip.member_id, VaultToken.active.is_(True)
    ).order_by(VaultToken.id.desc()))
    if token is None:
        raise PayPalError("Member has not saved PayPal")

    usd = inr_to_usd(booking.amount)
    key = uuid.uuid4().hex
    order = paypal_client.charge_vaulted(token.vault_id, usd, booking.label, request_id=key)
    if order.get("status") != "COMPLETED":
        raise PayPalError(f"Saved-PayPal charge not completed ({order.get('status')})")

    cap = order["purchase_units"][0]["payments"]["captures"][0]
    if Decimal(cap["amount"]["value"]) != usd:  # never keep money we did not ask for
        paypal_client.refund_capture(cap["id"], cap["amount"]["value"], note="Amount mismatch",
                                     request_id=key + "-mismatch")
        raise PayPalError("Charged amount did not match the booking; refunded")

    p = Payment(booking_id=booking.id, trip_id=booking.trip_id, member_id=trip.member_id,
                request_key=key, amount_inr=booking.amount, amount_usd=float(usd),
                status="CAPTURED", order_id=order["id"], capture_id=cap["id"])
    session.add(p)
    session.flush()
    return p

def has_saved_paypal(session: Session, member_id: str) -> bool:
    """True when the member saved PayPal, i.e. agreed to automatic payment."""
    if not config.USE_PAYPAL:
        return False
    return session.scalar(select(VaultToken.id).where(
        VaultToken.member_id == member_id, VaultToken.active.is_(True))) is not None

def start_vault_setup(session: Session, member_id: str) -> dict:
    """Step 1 of saving PayPal: get the consent link and remember who asked for it."""
    if session.get(Member, member_id) is None:
        raise PayPalError("Unknown member")
    res = paypal_client.create_setup_token()
    link = next((l["href"] for l in res.get("links", [])
                 if l["rel"] in ("approve", "payer-action")), None)
    if not link:
        raise PayPalError("PayPal gave no approval link")
    session.add(VaultSetup(setup_id=res["id"], member_id=member_id))
    session.flush()
    return {"approve_url": link}

def complete_vault_setup(session: Session, member_id: str, setup_id: str) -> dict:
    """Step 2 of saving PayPal: only the member who started the setup can finish it."""
    row = session.scalar(select(VaultSetup).where(
        VaultSetup.setup_id == setup_id, VaultSetup.member_id == member_id))
    if row is None:
        raise PayPalError("Unknown setup for this member")
    if row.status == "DONE":
        return {"saved": True}
    res = paypal_client.create_payment_token(setup_id, request_id=f"vault-{setup_id}")
    vault_id = res.get("id")
    if not vault_id:
        raise PayPalError("PayPal returned no saved payment token")
    for old in session.scalars(select(VaultToken).where(
            VaultToken.member_id == member_id, VaultToken.active.is_(True))).all():
        old.active = False
    session.add(VaultToken(member_id=member_id, vault_id=vault_id,
                           paypal_customer_id=(res.get("customer") or {}).get("id")))
    row.status = "DONE"
    session.flush()
    return {"saved": True}
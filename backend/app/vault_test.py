import sys
import uuid

from sqlalchemy import select

from app import paypal_client
from app.db import init_db, session_scope
from app.models import VaultToken

USAGE = "Usage: python -m app.vault_test start MEMBER_ID | finish ORDER_ID MEMBER_ID | show"
if len(sys.argv) < 2:
    sys.exit(USAGE)

init_db()  # makes sure the vault_tokens table exists
cmd = sys.argv[1]

if cmd == "start" and len(sys.argv) == 3:
    order = paypal_client.create_vault_order("1.00", "Waypoint: save PayPal for auto-rebooking",
                                             request_id=uuid.uuid4().hex)
    print("Order ID:", order["id"])
    print("Status:", order["status"])
    for link in order["links"]:
        if link["rel"] in ("approve", "payer-action"):
            print("Approve link:", link["href"])

elif cmd == "finish" and len(sys.argv) == 4:
    order_id, member_id = sys.argv[2], sys.argv[3]
    captured = paypal_client.capture_order(order_id)
    print("Capture status:", captured["status"])
    vault_id, customer_id = paypal_client.extract_vault(captured)
    if not vault_id:  # some responses only carry the token on a fresh GET
        vault_id, customer_id = paypal_client.extract_vault(paypal_client.get_order(order_id))
    if not vault_id:
        sys.exit("No vault token came back. Check that 'Save payment methods' is saved on the app.")
    with session_scope() as s:
        for old in s.scalars(select(VaultToken).where(VaultToken.member_id == member_id,
                                                      VaultToken.active.is_(True))).all():
            old.active = False
        s.add(VaultToken(member_id=member_id, vault_id=vault_id, paypal_customer_id=customer_id))
    print(f"Saved PayPal for {member_id} (token ends ...{vault_id[-4:]})")

elif cmd == "show":
    with session_scope() as s:
        for t in s.scalars(select(VaultToken).order_by(VaultToken.id)).all():
            print(t.id, t.member_id, "active" if t.active else "old", f"...{t.vault_id[-4:]}")

else:
    sys.exit(USAGE)
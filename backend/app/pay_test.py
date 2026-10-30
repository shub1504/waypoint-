import sys

from app import paypal_client

USAGE = ("Usage: python -m app.pay_test authorize ORDER_ID | capture AUTH_ID | "
         "refund CAPTURE_ID AMOUNT | void AUTH_ID")

if len(sys.argv) < 3:
    sys.exit(USAGE)

action, value = sys.argv[1], sys.argv[2]

if action == "authorize":
    result = paypal_client.authorize_order(value)
    auth = result["purchase_units"][0]["payments"]["authorizations"][0]
    print("Order status:", result["status"])
    print("Authorization ID:", auth["id"])
    print("Authorization status:", auth["status"])
elif action == "capture":
    result = paypal_client.capture_authorization(value)
    print("Capture ID:", result["id"])
    print("Capture status:", result["status"])
elif action == "refund" and len(sys.argv) == 4:
    result = paypal_client.refund_capture(value, sys.argv[3], note="Waypoint cancellation")
    print("Refund ID:", result["id"])
    print("Refund status:", result["status"])
elif action == "void":
    paypal_client.void_authorization(value)
    print("Authorization voided")
else:
    sys.exit(USAGE)
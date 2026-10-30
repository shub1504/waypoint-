from app import paypal_client

order = paypal_client.create_order(
    amount="120.00",
    description="Waypoint test rebooking: DEL to BOM",
)

print("Order ID:", order["id"])
print("Status:", order["status"])
for link in order["links"]:
    if link["rel"] in ("approve", "payer-action"):
        print("Approve link:", link["href"])
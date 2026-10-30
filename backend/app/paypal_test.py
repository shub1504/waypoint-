import requests
from app import config

print("Using base URL:", config.PAYPAL_BASE_URL)
print("Keys loaded:", config.USE_PAYPAL)

resp = requests.post(
    f"{config.PAYPAL_BASE_URL}/v1/oauth2/token",
    auth=(config.PAYPAL_CLIENT_ID, config.PAYPAL_CLIENT_SECRET),
    data={"grant_type": "client_credentials"},
    timeout=15,
)

print("HTTP status:", resp.status_code)
if resp.ok:
    body = resp.json()
    print("Token type:", body.get("token_type"))
    print("Expires in (sec):", body.get("expires_in"))
    print("Token received: YES")
else:
    print("Error:", resp.json().get("error"), "-", resp.json().get("error_description"))
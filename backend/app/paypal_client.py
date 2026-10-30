import re
import time
import uuid
from decimal import Decimal, InvalidOperation

import requests

from app import config

_token = {"value": None, "expires_at": 0.0}
_ID_RE = re.compile(r"^[A-Za-z0-9\-]{8,40}$")


class PayPalError(Exception):
    pass


def _get_token() -> str:
    """Fetch an access token, reusing it until shortly before it expires."""
    if _token["value"] and time.time() < _token["expires_at"] - 60:
        return _token["value"]
    if not config.USE_PAYPAL:
        raise PayPalError("PayPal keys are not configured")
    resp = requests.post(
        f"{config.PAYPAL_BASE_URL}/v1/oauth2/token",
        auth=(config.PAYPAL_CLIENT_ID, config.PAYPAL_CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
        timeout=15,
    )
    if not resp.ok:
        raise PayPalError(f"Token request failed ({resp.status_code})")
    body = resp.json()
    _token["value"] = body["access_token"]
    _token["expires_at"] = time.time() + body.get("expires_in", 300)
    return _token["value"]


def _headers(request_id: str | None = None) -> dict:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
        "PayPal-Request-Id": request_id or str(uuid.uuid4()),
    }


def _clean_id(value: str, label: str) -> str:
    """IDs go into URL paths, so only allow the characters PayPal IDs really use."""
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise PayPalError(f"Invalid {label}")
    return value


def _clean_amount(amount) -> str:
    """Server-side validation: never trust an amount that came from the frontend."""
    try:
        value = Decimal(str(amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise PayPalError("Invalid amount")
    if value <= 0 or value > Decimal("10000"):
        raise PayPalError("Amount out of allowed range")
    return str(value)


def create_order(amount, description: str, request_id: str | None = None,
                 intent: str = "AUTHORIZE") -> dict:
    """Create a sandbox order. request_id makes retries safe (no double orders)."""
    payload = {
        "intent": intent,
        "purchase_units": [{
            "description": description[:120],
            "amount": {"currency_code": "USD", "value": _clean_amount(amount)},
        }],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "return_url": "http://localhost:5173/payment/success",
                    "cancel_url": "http://localhost:5173/payment/cancel",
                    "user_action": "PAY_NOW",
                    "shipping_preference": "NO_SHIPPING",
                }
            }
        },
    }
    resp = requests.post(
        f"{config.PAYPAL_BASE_URL}/v2/checkout/orders",
        json=payload,
        headers=_headers(request_id),
        timeout=15,
    )
    if not resp.ok:
        raise PayPalError(f"Create order failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def authorize_order(order_id: str, request_id: str | None = None) -> dict:
    """After the buyer approved: place the hold. Money is reserved, not yet taken."""
    order_id = _clean_id(order_id, "order id")
    resp = requests.post(
        f"{config.PAYPAL_BASE_URL}/v2/checkout/orders/{order_id}/authorize",
        json={},
        headers=_headers(request_id),
        timeout=15,
    )
    if not resp.ok:
        raise PayPalError(f"Authorize failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def capture_authorization(authorization_id: str, request_id: str | None = None) -> dict:
    """Take the held money. Call this only after the booking is confirmed."""
    authorization_id = _clean_id(authorization_id, "authorization id")
    resp = requests.post(
        f"{config.PAYPAL_BASE_URL}/v2/payments/authorizations/{authorization_id}/capture",
        json={"final_capture": True},
        headers=_headers(request_id),
        timeout=15,
    )
    if not resp.ok:
        raise PayPalError(f"Capture failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()

def refund_capture(capture_id: str, amount, note: str = "",
                   request_id: str | None = None) -> dict:
    """Return money for a captured payment (full or partial)."""
    capture_id = _clean_id(capture_id, "capture id")
    payload = {
        "amount": {"currency_code": "USD", "value": _clean_amount(amount)},
        "note_to_payer": note[:120],
    }
    resp = requests.post(
        f"{config.PAYPAL_BASE_URL}/v2/payments/captures/{capture_id}/refund",
        json=payload,
        headers=_headers(request_id),
        timeout=15,
    )
    if not resp.ok:
        raise PayPalError(f"Refund failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def void_authorization(authorization_id: str, request_id: str | None = None) -> None:
    """Release a hold that was never captured (cancel before the booking is confirmed)."""
    authorization_id = _clean_id(authorization_id, "authorization id")
    resp = requests.post(
        f"{config.PAYPAL_BASE_URL}/v2/payments/authorizations/{authorization_id}/void",
        headers=_headers(request_id),
        timeout=15,
    )
    if not resp.ok:
        raise PayPalError(f"Void failed ({resp.status_code}): {resp.text[:300]}")

_RETURN_CTX = {
    "return_url": "http://localhost:5173/payment/success",
    "cancel_url": "http://localhost:5173/payment/cancel",
    "user_action": "PAY_NOW",
    "shipping_preference": "NO_SHIPPING",
}


def create_vault_order(amount, description: str, request_id: str | None = None) -> dict:
    """One-time purchase that also saves the member's PayPal for later charges (they approve once)."""
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "description": description[:120],
            "amount": {"currency_code": "USD", "value": _clean_amount(amount)},
        }],
        "payment_source": {"paypal": {
            "experience_context": _RETURN_CTX,
            "attributes": {"vault": {
                "store_in_vault": "ON_SUCCESS",
                "usage_type": "MERCHANT",
                "customer_type": "CONSUMER",
            }},
        }},
    }
    resp = requests.post(f"{config.PAYPAL_BASE_URL}/v2/checkout/orders", json=payload,
                         headers=_headers(request_id), timeout=15)
    if not resp.ok:
        raise PayPalError(f"Create vault order failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def capture_order(order_id: str, request_id: str | None = None) -> dict:
    order_id = _clean_id(order_id, "order id")
    resp = requests.post(f"{config.PAYPAL_BASE_URL}/v2/checkout/orders/{order_id}/capture",
                         json={}, headers=_headers(request_id), timeout=15)
    if not resp.ok:
        raise PayPalError(f"Capture order failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def get_order(order_id: str) -> dict:
    order_id = _clean_id(order_id, "order id")
    resp = requests.get(f"{config.PAYPAL_BASE_URL}/v2/checkout/orders/{order_id}",
                        headers=_headers(), timeout=15)
    if not resp.ok:
        raise PayPalError(f"Get order failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def extract_vault(order: dict) -> tuple[str | None, str | None]:
    """Pull the saved-payment token (and PayPal's customer id) out of a captured order."""
    vault = (order.get("payment_source", {}).get("paypal", {})
             .get("attributes", {}).get("vault", {}))
    return vault.get("id"), (vault.get("customer") or {}).get("id")

_VAULT_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{6,64}$")


def charge_vaulted(vault_id: str, amount, description: str, request_id: str | None = None) -> dict:
    """Charge a member's saved PayPal. No approval screen: they consented when they saved it."""
    if not isinstance(vault_id, str) or not _VAULT_ID_RE.match(vault_id):
        raise PayPalError("Invalid saved payment token")
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "description": description[:120],
            "amount": {"currency_code": "USD", "value": _clean_amount(amount)},
        }],
        "payment_source": {"paypal": {"vault_id": vault_id}},
    }
    resp = requests.post(f"{config.PAYPAL_BASE_URL}/v2/checkout/orders", json=payload,
                         headers=_headers(request_id), timeout=15)
    if not resp.ok:
        raise PayPalError(f"Saved-PayPal charge failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()

def create_setup_token(request_id: str | None = None) -> dict:
    """Ask PayPal for a consent link that saves the member's PayPal. Nothing is charged."""
    payload = {"payment_source": {"paypal": {
        "usage_type": "MERCHANT",
        "customer_type": "CONSUMER",
        "experience_context": {
            "return_url": "http://localhost:5173/payment/vault-success",
            "cancel_url": "http://localhost:5173/payment/vault-cancel",
        },
    }}}
    resp = requests.post(f"{config.PAYPAL_BASE_URL}/v3/vault/setup-tokens", json=payload,
                         headers=_headers(request_id), timeout=15)
    if not resp.ok:
        raise PayPalError(f"Create setup token failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()

def create_payment_token(setup_token_id: str, request_id: str | None = None) -> dict:
    """After the member approved: turn the setup token into the saved-PayPal token."""
    setup_token_id = _clean_id(setup_token_id, "setup token id")
    payload = {"payment_source": {"token": {"id": setup_token_id, "type": "SETUP_TOKEN"}}}
    resp = requests.post(f"{config.PAYPAL_BASE_URL}/v3/vault/payment-tokens", json=payload,
                         headers=_headers(request_id), timeout=15)
    if not resp.ok:
        raise PayPalError(f"Create payment token failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()
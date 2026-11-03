import httpx
from ..config import BOOKING_API_KEY, BOOKING_API_URL
from ..prompts.booking import BOOKING_SYSTEM
from ..llm import traced_node

@traced_node("payment_node")
async def payment_node(state):
    approval = state.get("payment_approval", {})
    if not approval.get("approved", False):
        return {"booking_result": {
            "status": "rejected",
            "message": "Payment/booking was not approved by the user."
        }}
    if not BOOKING_API_URL:
        return {"booking_result": {
            "status": "error",
            "message": "Human approval received, but BOOKING_API_URL is not configured."
        }}
    _ = BOOKING_SYSTEM
    payload = {
        "selection": state.get("selection", {}),
        "recommendations": state.get("recommendations", {}),
        "payment_approval": approval,
    }
    headers = {"Authorization": f"Bearer {BOOKING_API_KEY}"} if BOOKING_API_KEY else {}
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(BOOKING_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            provider_result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {"booking_result": {
            "status": "error",
            "message": f"Booking provider failed: {exc}",
        }}
    return {"booking_result": provider_result}

import httpx
from langchain_core.tools import tool
from ..config import HOTEL_API_KEY, HOTEL_API_URL

@tool
def search_hotels(preferences: dict):
    """Hotel research adapter. Connect a live hotel-search provider here."""
    if not HOTEL_API_URL:
        return {"error": "HOTEL_API_URL is not configured", "hotels": []}
    params = {
        "destination": preferences.get("destination"),
        "check_in": preferences.get("departure_date"),
        "check_out": preferences.get("return_date"),
        "budget_per_night_inr": preferences.get("hotel_budget_per_night_inr"),
        "area": preferences.get("hotel_area_preference"),
    }
    headers = {"Authorization": f"Bearer {HOTEL_API_KEY}"} if HOTEL_API_KEY else {}
    try:
        response = httpx.get(HOTEL_API_URL, params=params, headers=headers, timeout=45)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {"error": str(exc), "hotels": []}
    return data if isinstance(data, dict) else {"hotels": data}

import os, httpx
from langchain_core.tools import tool

def lookup_airport_candidates(query: str):
    # Keep this adapter provider-neutral; plug in your preferred airport lookup dataset/API.
    return []

@tool
def search_flights(preferences: dict):
    """Search HasData Google Flights for live flight options."""
    key = os.getenv("HASDATA_API_KEY")
    if not key:
        return {"error": "HASDATA_API_KEY is not configured", "flights": []}
    params = {
        "departureId": preferences.get("origin"),
        "arrivalId": preferences.get("destination"),
        "outboundDate": preferences.get("departure_date"),
    }
    if preferences.get("return_date"):
        params["returnDate"] = preferences["return_date"]
    try:
        r = httpx.get(
            "https://api.hasdata.com/scrape/google/flights",
            params=params,
            headers={"x-api-key": key},
            timeout=45
        )
        r.raise_for_status()
        data = r.json()
        return data
    except Exception as e:
        return {"error": str(e), "flights": []}

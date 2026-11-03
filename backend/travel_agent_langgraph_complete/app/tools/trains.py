import os, httpx
from langchain_core.tools import tool

BASE = "https://railradar.in"

def _headers():
    key = os.getenv("RAILRADAR_API_KEY")
    return {"Authorization": f"Bearer {key}"} if key else {}

def lookup_station_candidates(query: str):
    if not query: return []
    try:
        r = httpx.get(f"{BASE}/v1/lookup/search/stations", params={"query": query}, headers=_headers(), timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []

@tool
def search_trains(preferences: dict):
    """Search RailRadar for trains matching the user's origin, destination and date."""
    origin = preferences.get("origin","")
    destination = preferences.get("destination","")
    date = preferences.get("departure_date","")
    # Resolve codes in production using lookup_station_candidates and then call the
    # documented RailRadar between-stations endpoint.
    try:
        r = httpx.get(
            f"{BASE}/v1/trains/between/{origin}/{destination}",
            params={"date": date} if date else {},
            headers=_headers(), timeout=30
        )
        r.raise_for_status()
        data = r.json()
        return data.get("trains", data) if isinstance(data, dict) else data
    except Exception as e:
        return {"error": str(e), "trains": []}

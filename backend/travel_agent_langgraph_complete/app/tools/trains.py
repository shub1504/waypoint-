import os
from langchain_core.tools import tool
from app.live_providers import (
    search_trains_live,
    lookup_station_candidates as _lookup_station,
    resolve_station_code,
)

def lookup_station_candidates(query: str):
    if not query:
        return []
    code = resolve_station_code(query)
    if code:
        return [{"code": code, "name": query}]
    return []

@tool
def search_trains(preferences: dict):
    """Search RailRadar for trains matching the user's origin, destination and date."""
    origin = preferences.get("origin", "")
    destination = preferences.get("destination", "")
    date = preferences.get("departure_date", "")
    return search_trains_live(origin, destination, date)

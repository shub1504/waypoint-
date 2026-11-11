from langchain_core.tools import tool
from app.live_providers import search_flights_live, lookup_airport_candidates

@tool
def search_flights(preferences: dict):
    """Search HasData Google Flights for live flight options."""
    origin = preferences.get("origin", "")
    destination = preferences.get("destination", "")
    date = preferences.get("departure_date", "")
    return search_flights_live(origin, destination, date)

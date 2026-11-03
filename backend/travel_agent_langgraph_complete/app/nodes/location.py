from ..llm import get_llm, traced_node
from ..schemas import LocationResolution
from ..prompts.location import LOCATION_SYSTEM
from ..tools.trains import lookup_station_candidates
from ..tools.flights import lookup_airport_candidates
import asyncio

@traced_node("location_node")
async def location_node(state):
    p = state["preferences"]
    origins, destinations = await asyncio.gather(
        asyncio.to_thread(lookup_station_candidates, p.get("origin", "")),
        asyncio.to_thread(lookup_station_candidates, p.get("destination", "")),
    )
    if not origins:
        origins = await asyncio.to_thread(lookup_airport_candidates, p.get("origin", ""))
    if not destinations:
        destinations = await asyncio.to_thread(lookup_airport_candidates, p.get("destination", ""))
    llm = get_llm().with_structured_output(LocationResolution)
    prompt = f"Origin: {p.get('origin')} candidates: {origins}\nDestination: {p.get('destination')} candidates: {destinations}"
    result = await llm.ainvoke([("system", LOCATION_SYSTEM), ("human", prompt)])
    resolution = result.model_dump()
    return {
        "location_resolution": resolution,
        "assistant_message": resolution["explanation"] if resolution["needs_user_choice"] else "",
    }

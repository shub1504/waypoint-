from typing import Annotated, Any, Dict, List
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

class TravelState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    user_message: str
    intent: Dict[str, Any]
    preferences: Dict[str, Any]
    missing_fields: List[str]
    assistant_message: str
    location_resolution: Dict[str, Any]
    research_plan: Dict[str, Any]
    train_results: List[Dict[str, Any]]
    flight_results: List[Dict[str, Any]]
    hotel_results: List[Dict[str, Any]]
    recommendations: Dict[str, Any]
    selection: Dict[str, Any]
    payment_approval: Dict[str, Any]
    booking_result: Dict[str, Any]

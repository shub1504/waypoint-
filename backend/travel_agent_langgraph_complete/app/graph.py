from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.memory import MemorySaver
import logging
from .config import DATABASE_URL
from .state import TravelState
from .nodes.intent import intent_node
from .nodes.requirements import requirements_node
from .nodes.location import location_node
from .nodes.research import research_node
from .nodes.recommendations import recommendations_node
from .nodes.approval import selection_approval_node, payment_approval_node
from .nodes.payment import payment_node
from .llm import traced_node

def route_after_intent(state):
    return "requirements" if state["intent"]["is_travel"] else "reject"

def route_after_requirements(state):
    return "location" if not state.get("missing_fields") else "ask"

def route_after_location(state):
    resolution = state.get("location_resolution", {})
    return "ask" if resolution.get("needs_user_choice") else "research"

def route_after_recommendations(state):
    recommendations = state.get("recommendations", {})
    has_options = any(recommendations.get(category) for category in ("trains", "flights", "hotels"))
    return "selection_approval" if has_options else "no_results"

@traced_node("reject_node")
def reject_node(state):
    message = "I can only help with travel-related requests such as trip planning, trains, flights, hotels, itineraries, and travel bookings."
    return {"assistant_message": message, "messages": [{"role": "assistant", "content": message}]}

@traced_node("ask_node")
def ask_node(state):
    return {}

@traced_node("no_results_node")
def no_results_node(state):
    message = "I could not find any verified live options for those preferences. Please adjust the dates, locations, budget, or transport mode."
    return {"assistant_message": message, "messages": [{"role": "assistant", "content": message}]}

builder = StateGraph(TravelState)
builder.add_node("intent", intent_node)
builder.add_node("requirements", requirements_node)
builder.add_node("location", location_node)
builder.add_node("research", research_node)
builder.add_node("recommendations", recommendations_node)
builder.add_node("selection_approval", selection_approval_node)
builder.add_node("payment_approval", payment_approval_node)
builder.add_node("payment", payment_node)
builder.add_node("reject", reject_node)
builder.add_node("ask", ask_node)
builder.add_node("no_results", no_results_node)

builder.add_edge(START, "intent")
builder.add_conditional_edges("intent", route_after_intent, {"requirements":"requirements","reject":"reject"})
builder.add_conditional_edges("requirements", route_after_requirements, {"location":"location","ask":"ask"})
builder.add_conditional_edges("location", route_after_location, {"research": "research", "ask": "ask"})
builder.add_edge("research", "recommendations")
builder.add_conditional_edges(
    "recommendations",
    route_after_recommendations,
    {"selection_approval": "selection_approval", "no_results": "no_results"},
)
builder.add_edge("selection_approval", "payment_approval")
builder.add_edge("payment_approval", "payment")
builder.add_edge("payment", END)
builder.add_edge("reject", END)
builder.add_edge("ask", END)
builder.add_edge("no_results", END)

graph = None
_checkpointer_context = None
checkpointer_mode = "none"

async def startup():
    global graph, _checkpointer_context, checkpointer_mode
    if graph is not None:
        return graph
    if DATABASE_URL:
        try:
            _checkpointer_context = AsyncPostgresSaver.from_conn_string(DATABASE_URL)
            checkpointer = await _checkpointer_context.__aenter__()
            await checkpointer.setup()
            graph = builder.compile(checkpointer=checkpointer)
            checkpointer_mode = "postgres"
            return graph
        except Exception as exc:
            import logging
            logging.getLogger("travel_agent").warning(
                "PostgreSQL checkpointer startup failed, falling back to memory: %s", exc
            )
            if _checkpointer_context is not None:
                try:
                    await _checkpointer_context.__aexit__(None, None, None)
                except Exception:
                    pass
                _checkpointer_context = None

    from langgraph.checkpoint.memory import MemorySaver
    checkpointer = MemorySaver()
    graph = builder.compile(checkpointer=checkpointer)
    checkpointer_mode = "memory"
    return graph

async def shutdown():
    global _checkpointer_context, graph, checkpointer_mode
    if _checkpointer_context is not None:
        await _checkpointer_context.__aexit__(None, None, None)
    _checkpointer_context = None
    graph = None
    checkpointer_mode = "none"

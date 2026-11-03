from ..llm import get_llm, traced_node
from ..schemas import Recommendations
from ..prompts.recommendations import RECOMMENDATION_SYSTEM

@traced_node("recommendations_node")
async def recommendations_node(state):
    llm = get_llm().with_structured_output(Recommendations)
    payload = {
        "preferences": state["preferences"],
        "trains": state.get("train_results", []),
        "flights": state.get("flight_results", []),
        "hotels": state.get("hotel_results", [])
    }
    result = await llm.ainvoke([("system", RECOMMENDATION_SYSTEM), ("human", str(payload))])
    return {"recommendations": result.model_dump()}

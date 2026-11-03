from ..llm import get_llm, traced_node
from ..schemas import IntentResult
from ..prompts.intent import INTENT_SYSTEM

@traced_node("intent_node")
async def intent_node(state):
    llm = get_llm().with_structured_output(IntentResult)
    latest = state.get("user_message", "")
    messages = state.get("messages", [])
    if messages:
        latest_message = messages[-1]
        latest = getattr(latest_message, "content", latest) or latest
    result = await llm.ainvoke([("system", INTENT_SYSTEM), ("human", latest)])
    return {"intent": result.model_dump()}

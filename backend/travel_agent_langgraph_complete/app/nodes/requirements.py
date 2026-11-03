from ..llm import get_llm, traced_node
from ..schemas import RequirementResult
from ..prompts.requirements import REQUIREMENTS_SYSTEM
from langchain_core.messages import AIMessage

@traced_node("requirements_node")
async def requirements_node(state):
    llm = get_llm().with_structured_output(RequirementResult)
    prior = state.get("preferences", {})
    history = "\n".join(
        f"{getattr(message, 'type', 'message')}: {getattr(message, 'content', message)}"
        for message in state.get("messages", [])
    )
    prompt = (
        f"Existing preferences: {prior}\n"
        f"Conversation history:\n{history}\n"
        f"Latest user message: {state.get('user_message', '')}"
    )
    result = await llm.ainvoke([("system", REQUIREMENTS_SYSTEM), ("human", prompt)])
    update = result.model_dump()
    response = "\n".join(update["questions"]) if update["questions"] else ""
    result_state = {
        "preferences": update["preferences"],
        "missing_fields": update["missing_required_fields"],
        "assistant_message": response,
    }
    if response:
        result_state["messages"] = [AIMessage(content=response)]
    return result_state

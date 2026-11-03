from langchain_core.messages import HumanMessage
from .graph import startup

async def run(user_message: str, thread_id: str = "demo-user"):
    graph = await startup()
    config = {"configurable": {"thread_id": thread_id}}
    return await graph.ainvoke(
        {"user_message": user_message, "messages": [HumanMessage(content=user_message)]},
        config=config,
    )

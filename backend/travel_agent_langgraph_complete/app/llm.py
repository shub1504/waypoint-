from langchain_google_genai import ChatGoogleGenerativeAI
from langsmith import traceable
from .config import MODEL_NAME

def get_llm():
    return ChatGoogleGenerativeAI(model=MODEL_NAME, temperature=0)

def traced_node(name: str):
    return traceable(
        name=name,
        run_type="chain",
        tags=["travel-agent", f"node:{name}"],
        metadata={"component": "travel_agent_langgraph_complete"},
    )

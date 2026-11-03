import asyncio
from ..llm import get_llm, traced_node
from ..schemas import ResearchPlan
from ..prompts.research import RESEARCH_SYSTEM
from ..tools.trains import search_trains
from ..tools.flights import search_flights
from ..tools.hotels import search_hotels

@traced_node("research_node")
async def research_node(state):
    llm = get_llm().with_structured_output(ResearchPlan)
    plan = await llm.ainvoke([("system", RESEARCH_SYSTEM), ("human", str(state["preferences"]))])
    p = state["preferences"]
    tasks = []
    names = []
    if plan.search_trains:
        tasks.append(search_trains.ainvoke(p)); names.append("train")
    if plan.search_flights:
        tasks.append(search_flights.ainvoke(p)); names.append("flight")
    if plan.search_hotels:
        tasks.append(search_hotels.ainvoke(p)); names.append("hotel")
    values = await asyncio.gather(*tasks, return_exceptions=True)
    out = {"research_plan": plan.model_dump()}
    for name, value in zip(names, values):
        out[name + "_results"] = (
            {"error": str(value), name + "s": []}
            if isinstance(value, Exception)
            else value
        )
    return out

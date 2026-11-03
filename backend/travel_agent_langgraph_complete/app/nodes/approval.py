from langgraph.types import interrupt
from ..llm import get_llm, traced_node
from ..prompts.selection import SELECTION_SYSTEM
from ..prompts.payment import PAYMENT_SYSTEM
from ..schemas import PaymentApproval, Selection

@traced_node("selection_approval_node")
async def selection_approval_node(state):
    recommendations = state.get("recommendations", {})
    valid_ids = {
        option["option_id"]
        for category in ("trains", "flights", "hotels")
        for option in recommendations.get(category, [])
        if option.get("option_id")
    }
    while True:
        answer = interrupt({
            "type": "selection_approval",
            "message": "Select one or more displayed option IDs to proceed.",
            "recommendations": recommendations,
            "valid_option_ids": sorted(valid_ids),
        })
        parsed = await get_llm().with_structured_output(Selection).ainvoke([
            ("system", SELECTION_SYSTEM),
            ("human", f"Recommendations: {recommendations}\nUser selection: {answer}"),
        ])
        ids = parsed.approved_option_ids
        if (
            isinstance(ids, list)
            and ids
            and all(isinstance(item, str) for item in ids)
            and len(ids) == len(set(ids))
            and set(ids).issubset(valid_ids)
        ):
            return {"selection": parsed.model_dump()}

@traced_node("payment_approval_node")
async def payment_approval_node(state):
    selected_ids = set(state.get("selection", {}).get("approved_option_ids", []))
    selected = [
        option
        for category in ("trains", "flights", "hotels")
        for option in state.get("recommendations", {}).get(category, [])
        if option.get("option_id") in selected_ids
    ]
    total = sum(option.get("price_inr") or 0 for option in selected)
    while True:
        answer = interrupt({
            "type": "payment_approval",
            "message": "FINAL APPROVAL REQUIRED. Approve this exact selection and amount.",
            "selected_options": selected,
            "total_price_inr": total,
        })
        parsed = await get_llm().with_structured_output(PaymentApproval).ainvoke([
            ("system", PAYMENT_SYSTEM),
            ("human", f"Selected options: {selected}\nExact total: {total:.2f} INR\nUser approval: {answer}"),
        ])
        if parsed.approved and parsed.confirmation_text == f"APPROVE {total:.2f} INR":
            return {"payment_approval": parsed.model_dump()}

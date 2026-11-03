import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from .graph import shutdown, startup


class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=20_000)


class ResumeRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=200)
    decision: dict[str, Any]


@asynccontextmanager
async def lifespan(_: FastAPI):
    await startup()
    try:
        yield
    finally:
        await shutdown()


app = FastAPI(
    title="Waypoint Travel Agent API",
    version="1.0.0",
    description="Async, durable, human-approved travel planning API.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


def _sse(event: str, payload: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


async def _stream(thread_id: str, input_data: Any) -> AsyncIterator[str]:
    graph = await startup()
    config = {"configurable": {"thread_id": thread_id}}
    try:
        async for event in graph.astream_events(input_data, config=config, version="v2"):
            event_name = event.get("event", "")
            if event_name == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                content = getattr(chunk, "content", None)
                if content:
                    yield _sse("token", {"content": content})
            elif event_name in {"on_chain_start", "on_chain_end", "on_tool_start", "on_tool_end"}:
                yield _sse("progress", {
                    "event": event_name,
                    "name": event.get("name"),
                })
        snapshot = await graph.aget_state(config)
        interrupts = [
            item.value for task in snapshot.tasks for item in task.interrupts
        ]
        if interrupts:
            yield _sse("interrupt", {"payload": interrupts[0]})
        else:
            yield _sse("complete", {"state": snapshot.values})
    except Exception as exc:
        yield _sse("error", {"message": str(exc)})


@app.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream(
            request.thread_id,
            {
                "user_message": request.message,
                "messages": [HumanMessage(content=request.message)],
            },
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/resume")
async def resume(request: ResumeRequest) -> StreamingResponse:
    graph = await startup()
    snapshot = await graph.aget_state(
        {"configurable": {"thread_id": request.thread_id}}
    )
    if not any(task.interrupts for task in snapshot.tasks):
        raise HTTPException(status_code=409, detail="Thread is not awaiting human approval")
    return StreamingResponse(
        _stream(request.thread_id, Command(resume=request.decision)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/state/{thread_id}")
async def state(thread_id: str) -> dict[str, Any]:
    graph = await startup()
    snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    interrupts = [item.value for task in snapshot.tasks for item in task.interrupts]
    return {"values": snapshot.values, "interrupts": interrupts}

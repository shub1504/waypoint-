# Complete LangGraph Travel Agent

A stateful travel-agent using LangGraph, Pydantic structured output, durable PostgreSQL
checkpoint memory, parallel research tools, strict human-in-the-loop interrupts,
async FastAPI/SSE streaming, and LangSmith tracing.

## Core behavior

1. Strictly reject non-travel requests.
2. Extract travel requirements and ask only for missing information.
3. Resolve locations.
4. Research trains/flights/hotels in parallel.
5. Rank up to five real options per category.
6. Pause for explicit user selection.
7. Pause again for explicit final payment/booking approval.
8. Never perform payment/booking without approval.

## System prompts and tracing

Every LLM node imports its dedicated prompt from `app/prompts/` and uses structured
Pydantic output. Selection and payment approvals are also validated with their
dedicated prompts after the human interrupt. Every graph node has an explicit
LangSmith trace span tagged with its node name; LangChain tools and model calls are
nested automatically when `LANGSMITH_TRACING=true`.

## Setup

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill in:
- GOOGLE_API_KEY
- RAILRADAR_API_KEY
- HASDATA_API_KEY
- HOTEL_API_KEY
- HOTEL_API_URL
- BOOKING_API_URL
- BOOKING_API_KEY (optional)
- LANGSMITH_API_KEY
- LANGSMITH_TRACING=true
- LANGSMITH_PROJECT=travel-agent

## Run

Start PostgreSQL and set `TRAVEL_AGENT_DATABASE_URL` in the travel-agent `.env`.
For backward compatibility, a PostgreSQL `DATABASE_URL` in that same file is also
accepted. The application creates the LangGraph
checkpoint tables on startup; no in-memory state is used.

```bash
python run_server.py
```

On Windows, use `python run_server.py` rather than invoking Uvicorn directly.
The launcher configures the selector event loop before Uvicorn creates its server
loop, which is required by psycopg's async PostgreSQL driver.

The API is frontend-ready:

- `POST /api/travel-agent/chat` with `{"thread_id":"...", "message":"..."}` streams `progress`, `token`,
  `interrupt`, `complete`, and `error` SSE events.
- `POST /api/travel-agent/resume` with `{"thread_id":"...", "decision":{...}}` resumes a paused approval.
- `GET /api/travel-agent/state/{thread_id}` returns persisted values and pending interrupts.

The main Waypoint backend mounts the travel agent under `/api/travel-agent`; both services
share the same FastAPI lifecycle and CORS policy. The same `thread_id` must be used for every message and approval. The message reducer
persists the complete conversation history in the PostgreSQL checkpoint.

On Windows, the main backend configures the selector event loop required by psycopg's
async PostgreSQL driver before opening the LangGraph checkpointer.

## Feature audit

- Travel-only intent rejection: implemented.
- Requirement extraction and short-term conversation memory: implemented.
- Location disambiguation: implemented.
- Parallel train, flight, and hotel research: implemented; hotel access requires
  the configured generic `HOTEL_API_URL`.
- Up to five verified recommendations per category: implemented.
- Selection and final payment human approval interrupts: implemented and server-validated.
- Durable PostgreSQL checkpointer: implemented.
- Async FastAPI SSE streaming: implemented.
- LangSmith tracing on every graph node: implemented.
- Booking/payment execution: implemented through the configured `BOOKING_API_URL`;
  without it, the agent returns an explicit error and never claims success.

## Production integration

- Resolve city/station/airport names into provider IDs before live searches.
- Normalize provider responses into strict internal schemas.
- Revalidate price and availability immediately before booking.
- Never put card/UPI credentials into LLM prompts or graph state.

## LangSmith

LangChain/LangGraph tracing is enabled through the standard environment variables. Use the same project name across development/staging/production as appropriate.

## Suggested production API

Wrap the graph in FastAPI and expose:
- POST /chat
- POST /resume
- GET /state/{thread_id}

When a node calls `interrupt()`, persist the thread and return the approval payload to the frontend. Resume the same `thread_id` with the user's explicit decision.

## Security

The agent is not authorized to invent transaction data. The payment boundary is intentionally isolated and requires an explicit human approval after selection.

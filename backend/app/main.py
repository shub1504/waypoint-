"""FastAPI app: REST for the React UI, a WebSocket for the live feed, and the bus consumer."""
import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import agent, cancel, chat, chat_agent, config, explore, guardrail, trips as trips_mod
from app.bus import make_bus
from app.db import engine, init_db, session_scope
from app.models import Booking, Decision, Member, Trip
from app.scenarios import SCENARIOS, build_booking_event, build_event
from app.seed import create_member, seed
from app.otp_testing import generate_otp, verify_otp

log = logging.getLogger("waypoint")
logging.basicConfig(level=logging.INFO)


class Hub:
    """Fan-out of live messages to every open browser tab."""

    def __init__(self) -> None:
        self.sockets: set[WebSocket] = set()

    async def broadcast(self, msg: dict) -> None:
        dead = []
        for ws in self.sockets:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.sockets.discard(ws)


hub = Hub()
bus = make_bus()


def decision_dict(d: Decision) -> dict:
    return dict(
        id=d.id, event_id=d.event_id, member_id=d.member_id, trip_id=d.trip_id, booking_id=d.booking_id,
        event_type=d.event_type, status=d.status, kind=d.kind, payment_type=d.payment_type,
        original_amount=d.original_amount, ceiling=d.ceiling, pool_credit_used=d.pool_credit_used,
        chosen_amount=d.chosen_amount, chosen_label=d.chosen_label,
        options=json.loads(d.options_json) if d.options_json else [],
        reasoning=d.reasoning, notification=d.notification, channel=d.channel,
        latency_ms=d.latency_ms, created_at=d.created_at.isoformat() + "Z",
        resolved_at=d.resolved_at.isoformat() + "Z" if d.resolved_at else None,
    )


async def on_event(payload: dict) -> None:
    """Called for every event that comes off the bus."""
    await hub.broadcast({"type": "event", "data": payload})

    def work():
        with session_scope() as s:
            d = agent.handle_event(s, payload)
            return decision_dict(d) if d else None

    out = await asyncio.to_thread(work)
    if out:
        await hub.broadcast({"type": "decision", "data": out})
        await hub.broadcast({"type": "trips_changed"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with session_scope() as s:
        if seed(s):
            log.info("Seeded demo data")
    task = asyncio.create_task(bus.consume(on_event))
    log.info("Event bus: %s | DB: %s", bus.name, engine.dialect.name)
    yield
    task.cancel()
    await bus.close()


app = FastAPI(title="Waypoint â€” Disruption Concierge", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])




class OTPRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)


class OTPVerify(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    otp: str = Field(pattern=r"^\d{6}$")


@app.post("/api/auth/request-otp")
def request_otp(body: OTPRequest):
    email = body.email.strip().lower()

    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=400, detail="Enter a valid email address")

    generate_otp(email)
    return {
        "ok": True,
        "message": "Testing OTP generated. Check the backend terminal."
    }


@app.post("/api/auth/verify-otp")
def verify_otp_route(body: OTPVerify):
    email = body.email.strip().lower()

    if verify_otp(email, body.otp):
        return {
            "ok": True,
            "verified": True,
            "message": "OTP verified successfully"
        }

    raise HTTPException(status_code=400, detail="Invalid or expired OTP")

@app.get("/api/health")
def health():
    return {"ok": True, "bus": bus.name, "db": engine.dialect.name,
            "chat": "adk" if chat_agent.available() else "rules"}


@app.get("/api/rules")
def rules():
    """The guardrail multipliers, so the UI never hard-codes numbers that could drift."""
    return dict(prepaid=guardrail.PREPAID_MULT, pay_after=guardrail.PAY_AFTER_MULT, trip_cap=guardrail.TRIP_CAP_MULT)


@app.get("/api/scenarios")
def scenarios():
    return [{"id": k, "title": v["title"], "slide": v["slide"], "member": v["member"]} for k, v in SCENARIOS.items()]


@app.get("/api/trips")
def trips():
    with session_scope() as s:
        out = []
        for t in s.scalars(select(Trip)).all():
            m = s.get(Member, t.member_id)
            bks = s.scalars(select(Booking).where(Booking.trip_id == t.id).order_by(Booking.created_at)).all()
            active = [b for b in bks if b.status == "ACTIVE"]
            out.append(dict(
                id=t.id, title=t.title, purpose=t.purpose_place, envelope=t.envelope, pool_credit=t.pool_credit,
                spent=sum(b.amount for b in active),
                member=dict(id=m.id, name=m.name, budget_level=m.budget_level, channel=m.alert_channel,
                            consent_autorebook=m.consent_autorebook),
                bookings=[explore.with_limit(explore.booking_dict(b), b, t, m) for b in bks],
            ))
        return out


class TransportIn(BaseModel):
    kind: str = Field(pattern="^(FLIGHT|TRAIN|BUS)$")
    origin: str
    destination: str
    name: str = ""
    price: float = Field(gt=0)


class HotelIn(BaseModel):
    name: str
    area: str = ""
    distance_km: float = Field(default=1.0, ge=0)
    nights: int = Field(default=1, ge=1, le=60)
    price_per_night: float = Field(gt=0)


class TripIn(BaseModel):
    member_id: str
    title: str = ""
    destination: str
    purpose_type: str = Field(pattern="^(temple|business|monument|leisure)$")
    purpose_place: str = ""
    transports: list[TransportIn] = []
    hotels: list[HotelIn] = []


@app.post("/api/trips")
async def add_trip(body: TripIn):
    try:
        with session_scope() as s:
            t = trips_mod.create_trip(s, body.member_id, body.model_dump())
            out = dict(id=t.id, title=t.title, envelope=t.envelope)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await hub.broadcast({"type": "trips_changed"})
    return out


class CancelIn(BaseModel):
    trip_id: str
    booking_id: str | None = None  # None = the whole trip
    reason: str
    note: str = ""


@app.get("/api/cancel/reasons")
def cancel_reasons():
    return [dict(id=k, **v) for k, v in cancel.REASONS.items()]


@app.post("/api/cancel/preview")
def cancel_preview(body: CancelIn):
    try:
        with session_scope() as s:
            return cancel.plan(s, body.trip_id, body.booking_id, body.reason, body.note)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/cancel")
async def cancel_now(body: CancelIn):
    out = _answer(cancel.apply, body.trip_id, body.booking_id, body.reason, body.note)
    await hub.broadcast({"type": "decision", "data": out})
    await hub.broadcast({"type": "trips_changed"})
    return out


@app.get("/api/decisions")
def decisions():
    with session_scope() as s:
        rows = s.scalars(select(Decision).order_by(Decision.id.desc()).limit(50)).all()
        return [decision_dict(d) for d in rows]


@app.post("/api/simulate/{scenario_id}")
async def simulate(scenario_id: str, member: str | None = None):
    if scenario_id not in SCENARIOS:
        raise HTTPException(404, "Unknown scenario")
    with session_scope() as s:
        event = build_event(s, scenario_id, member)
    if event is None:
        raise HTTPException(409, "No active booking of that kind is left on this account. Add a trip or press Reset demo data.")
    await bus.publish(event)  # goes through Event Hubs when configured
    return {"published": event["event_id"], "bus": bus.name}


class BookingEventIn(BaseModel):
    booking_id: str
    type: str
    delay_hours: float = 0
    demand_spike: bool = False


@app.post("/api/simulate-booking")
async def simulate_booking(body: BookingEventIn):
    """Fire a disruption at one specific booking of a trip the member entered."""
    try:
        with session_scope() as s:
            event = build_booking_event(s, body.booking_id, body.type, body.delay_hours, body.demand_spike)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await bus.publish(event)
    return {"published": event["event_id"], "bus": bus.name}


@app.post("/api/reset")
async def reset():
    with session_scope() as s:
        seed(s, force=True)
    chat_agent.reset_sessions()
    await hub.broadcast({"type": "reset"})
    return {"ok": True}


def _answer(fn, *args):
    try:
        with session_scope() as s:
            return decision_dict(fn(s, *args))
    except (ValueError, IndexError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/decisions/{decision_id}/approve")
async def approve(decision_id: int):
    out = _answer(agent.approve, decision_id)
    await hub.broadcast({"type": "decision", "data": out})
    await hub.broadcast({"type": "trips_changed"})
    return out


@app.post("/api/decisions/{decision_id}/decline")
async def decline(decision_id: int):
    out = _answer(agent.decline, decision_id)
    await hub.broadcast({"type": "decision", "data": out})
    return out


@app.post("/api/decisions/{decision_id}/choose/{option_index}")
async def choose(decision_id: int, option_index: int):
    out = _answer(agent.choose, decision_id, option_index)
    await hub.broadcast({"type": "decision", "data": out})
    await hub.broadcast({"type": "trips_changed"})
    return out


# ------------------------------------------------------------------ profile / explore / chat
def member_dict(m: Member) -> dict:
    return dict(id=m.id, name=m.name, email=m.email, phone=m.phone, home_city=m.home_city,
                budget_level=m.budget_level, alert_channel=m.alert_channel,
                consent_autorebook=m.consent_autorebook, consent_history=m.consent_history)


class MemberUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    budget_level: str | None = None
    alert_channel: str | None = None
    home_city: str | None = None
    consent_autorebook: bool | None = None
    consent_history: bool | None = None


class ChatIn(BaseModel):
    member_id: str
    text: str


class SwitchIn(BaseModel):
    label: str


@app.get("/api/members")
def members():
    with session_scope() as s:
        return [member_dict(m) for m in s.scalars(select(Member).order_by(Member.id)).all()]


class MemberCreate(BaseModel):
    name: str
    email: str
    phone: str = ""
    home_city: str = "Delhi"
    budget_level: str = "medium"
    alert_channel: str = "Push"


@app.post("/api/members")
async def add_member(body: MemberCreate):
    if not body.name.strip() or not body.email.strip():
        raise HTTPException(400, "Name and email are required")
    if body.budget_level not in ("low", "medium", "high"):
        raise HTTPException(400, "budget_level must be low, medium or high")
    if body.alert_channel not in ("SMS", "Email", "Push"):
        raise HTTPException(400, "alert_channel must be SMS, Email or Push")
    with session_scope() as s:
        m = create_member(s, body.name.strip(), body.email.strip(), body.phone.strip(),
                          body.home_city.strip() or "Delhi", body.budget_level, body.alert_channel)
        out = member_dict(m)
    await hub.broadcast({"type": "member_added", "data": out})
    return out


@app.patch("/api/members/{member_id}")
async def update_member(member_id: str, body: MemberUpdate):
    if body.budget_level not in (None, "low", "medium", "high"):
        raise HTTPException(400, "budget_level must be low, medium or high")
    if body.alert_channel not in (None, "SMS", "Email", "Push"):
        raise HTTPException(400, "alert_channel must be SMS, Email or Push")
    for f in ("name", "email", "phone"):
        v = getattr(body, f)
        if v is not None and not v.strip():
            raise HTTPException(400, f"{f} cannot be empty")
        if v is not None:
            setattr(body, f, v.strip())
    with session_scope() as s:
        m = s.get(Member, member_id)
        if m is None:
            raise HTTPException(404, "Unknown member")
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(m, k, v)
        out = member_dict(m)
    await hub.broadcast({"type": "member_changed", "data": out})
    return out


@app.get("/api/members/{member_id}/bookings")
def member_bookings(member_id: str):
    with session_scope() as s:
        if s.get(Member, member_id) is None:
            raise HTTPException(404, "Unknown member")
        return explore.bookings_payload(s, member_id)


@app.get("/api/bookings/{booking_id}/options")
def booking_options(booking_id: str):
    try:
        with session_scope() as s:
            return explore.options_payload(s, booking_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/api/bookings/{booking_id}/switch")
async def booking_switch(booking_id: str, body: SwitchIn):
    out = _answer(explore.switch, booking_id, body.label)
    await hub.broadcast({"type": "decision", "data": out})
    await hub.broadcast({"type": "trips_changed"})
    return out


@app.post("/api/chat")
async def chat_reply(body: ChatIn):
    """Google ADK agent (Gemini) when a key is set; the keyword rules otherwise or if the model fails."""
    with session_scope() as s:
        if s.get(Member, body.member_id) is None:
            raise HTTPException(404, "Unknown member")
    if chat_agent.available():
        try:
            out = await chat_agent.ask(body.member_id, body.text)
            return dict(reply=out["reply"], actions=out["actions"], suggestions=chat.SUGGESTIONS, engine="adk")
        except Exception as e:  # quota, bad key, offline: never leave the member without an answer
            log.warning("ADK chat failed, using rules: %s", e)
    with session_scope() as s:
        return dict(**chat.reply(s, body.member_id, body.text), actions=[], engine="rules")


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    hub.sockets.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive; the UI never needs to send
    except WebSocketDisconnect:
        hub.sockets.discard(websocket)




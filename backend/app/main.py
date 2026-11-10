"""FastAPI app: REST for the React UI, a WebSocket for the live feed, and the bus consumer."""
import asyncio
from datetime import datetime
import json
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import agent, cancel, chat, chat_agent, config, explore, guardrail, journey, payments, trips as trips_mod
from app.bus import make_bus
from app.db import engine, init_db, session_scope
from app.models import Booking, Decision, Member, Payment, Trip
from app.paypal_client import PayPalError
from app.scenarios import SCENARIOS, build_booking_event, build_event
from app.seed import create_member, seed
from app.otp_testing import generate_otp, verify_otp
try:
    from travel_agent_langgraph_complete.app.api import app as travel_agent_app
    from travel_agent_langgraph_complete.app.graph import shutdown as shutdown_travel_agent
    from travel_agent_langgraph_complete.app.graph import startup as startup_travel_agent
except Exception as exc:  # agent packages ya Postgres na ho toh bhi Waypoint chalti rahe
    travel_agent_app = None
    logging.getLogger("waypoint").warning("Travel agent disabled: %s", exc)
travel_agent_ready = False  # becomes True only if the travel agent really started (the UI reads this from /api/health)
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
    log.info("Event received: %s (%s)", payload.get("event_id"), payload.get("type"))
    await hub.broadcast({"type": "event", "data": payload})

    def work():
        with session_scope() as s:
            d = agent.handle_event(s, payload)
            return decision_dict(d) if d else None

    try:
        out = await asyncio.to_thread(work)
    except Exception:
        log.exception("Handling event %s failed", payload.get("event_id"))
        return
    if not out:
        log.info("Event %s produced no decision", payload.get("event_id"))
        return
    await hub.broadcast({"type": "decision", "data": out})
    await hub.broadcast({"type": "trips_changed"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    global travel_agent_ready
    init_db()
    with session_scope() as s:
        if seed(s):
            log.info("Seeded demo data")
    agent_up = False
    if travel_agent_app is not None:
        try:
            await startup_travel_agent()
            agent_up = True
            travel_agent_ready = True
        except Exception as exc:  # jaise Postgres chal nahi raha
            log.warning("Travel agent startup failed, continuing without it: %s", exc)
    task = asyncio.create_task(bus.consume(on_event))
    log.info("Event bus: %s | DB: %s", bus.name, engine.dialect.name)
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        if agent_up:
            await shutdown_travel_agent()
        await bus.close()


app = FastAPI(title="Waypoint - Disruption Concierge", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
if travel_agent_app is not None:
    app.mount("/api/travel-agent", travel_agent_app)


def _combined_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    travel_schema = travel_agent_app.openapi() if travel_agent_app is not None else {}
    for path, path_schema in travel_schema.get("paths", {}).items():
        schema["paths"][f"/api/travel-agent{path}"] = path_schema
    components = schema.setdefault("components", {})
    for component_type, values in travel_schema.get("components", {}).items():
        components.setdefault(component_type, {}).update(values)
    app.openapi_schema = schema
    return schema


app.openapi = _combined_openapi


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
            "chat": "adk" if chat_agent.available() else "rules",
            "travel_agent": travel_agent_ready}


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


# ------------------------------------------------------------------ start a journey
STATION_CODE_RE = re.compile(r"^[A-Z]{2,5}$")


class JourneyBookIn(BaseModel):
    member_id: str
    train_no: str
    cls: str
    date: str
    from_station: str = Field(alias="from")
    to_station: str = Field(alias="to")
    budget: float = Field(gt=0)
    confirm_over_budget: bool = False

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }


@app.get("/api/journey/stations")
def journey_stations():
    return [{"code": code, "name": name} for code, name in journey.STATION_NAMES.items()]


@app.get("/api/journey/search")
def search_journey(
    from_station: str = Query(..., alias="from"),
    to_station: str = Query(..., alias="to"),
    date: str = Query(...),
    budget: float = Query(...),
):
    orig = from_station.strip().upper()
    dest = to_station.strip().upper()
    date_str = date.strip()

    if not STATION_CODE_RE.match(orig) or not STATION_CODE_RE.match(dest):
        raise HTTPException(400, "Station codes must be 2 to 5 letters (e.g. NDLS, UJN)")
    if orig == dest:
        raise HTTPException(400, "Origin and destination stations cannot be the same")
    if budget <= 0:
        raise HTTPException(400, "Budget must be greater than zero")

    try:
        journey_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date format. Expected YYYY-MM-DD")

    if journey_date < datetime.now().date():
        raise HTTPException(400, "Journey date must be today or later")

    return journey.search_journey(orig, dest, date_str, budget)


@app.post("/api/journey/book")
async def book_journey(body: JourneyBookIn):
    orig = body.from_station.strip().upper()
    dest = body.to_station.strip().upper()
    date_str = body.date.strip()
    train_no = str(body.train_no).strip()
    cls_name = body.cls.strip().upper()

    if not STATION_CODE_RE.match(orig) or not STATION_CODE_RE.match(dest):
        raise HTTPException(400, "Station codes must be 2 to 5 letters (e.g. NDLS, UJN)")
    if orig == dest:
        raise HTTPException(400, "Origin and destination stations cannot be the same")

    try:
        journey_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date format. Expected YYYY-MM-DD")

    if journey_date < datetime.now().date():
        raise HTTPException(400, "Journey date must be today or later")

    if cls_name not in journey.CLASSES:
        raise HTTPException(400, f"Invalid class '{cls_name}'. Must be one of: {', '.join(journey.CLASSES)}")

    # Deterministic simulation: recompute fare on the server; NEVER trust client-sent fare
    simulated_trains = journey.simulate_trains(orig, dest, date_str)
    matched_train = next((t for t in simulated_trains if t["train_no"] == train_no), None)
    if matched_train is None:
        raise HTTPException(400, f"Train {train_no} not found for route {orig} to {dest} on {date_str}")

    matched_cls = next((c for c in matched_train["classes"] if c["cls"].upper() == cls_name), None)
    if matched_cls is None:
        raise HTTPException(400, f"Class {cls_name} not available on train {train_no}")

    # Waitlisted (WL) classes cannot be booked
    if matched_cls["availability"].startswith("WL") or not matched_cls.get("available", True):
        raise HTTPException(400, f"Waitlisted (WL) classes cannot be booked ({matched_cls['availability']})")

    fare = float(matched_cls["fare"])

    # Over-budget check: require explicit confirmation
    if fare > body.budget and not body.confirm_over_budget:
        raise HTTPException(409, "This fare is over your budget. Please confirm to continue.")

    orig_name = journey.STATION_NAMES.get(orig, orig)
    dest_name = journey.STATION_NAMES.get(dest, dest)
    trip_title = f"{orig_name} to {dest_name} on {date_str}"
    booking_name = f"{matched_train['name']} ({cls_name}) {date_str}"
    expected_label = f"{booking_name} {trips_mod._place(orig)}\u2192{trips_mod._place(dest)}"

    try:
        with session_scope() as s:
            member = s.get(Member, body.member_id)
            if member is None:
                raise HTTPException(400, "Unknown member")

            # Check saved PayPal before creating any record
            if not payments.has_saved_paypal(s, body.member_id):
                raise HTTPException(400, "Member has not saved PayPal")

            # Duplicate guard: return 409 if active booking with same label already exists
            existing = s.scalar(
                select(Booking.id)
                .join(Trip, Trip.id == Booking.trip_id)
                .where(
                    Trip.member_id == body.member_id,
                    Booking.kind == "TRAIN",
                    Booking.status == "ACTIVE",
                    Booking.label == expected_label,
                )
            )
            if existing:
                raise HTTPException(409, "You already booked this train")

            trip_data = {
                "destination": dest,
                "title": trip_title,
                "purpose_type": "leisure",
                "purpose_place": dest_name,
                "transports": [
                    {
                        "kind": "TRAIN",
                        "origin": orig,
                        "destination": dest,
                        "name": booking_name,
                        "price": fare,
                    }
                ],
                "hotels": [],
            }

            trip = trips_mod.create_trip(s, body.member_id, trip_data)
            booking = s.scalar(select(Booking).where(Booking.trip_id == trip.id, Booking.status == "ACTIVE"))
            if booking is None:
                raise HTTPException(500, "Failed to create booking")

            # Charge saved PayPal; roll back on failure so no orphaned records exist
            try:
                payment = payments.charge_saved(s, booking.id)
            except PayPalError as e:
                log.warning("PayPal charge for journey booking %s failed: %s", booking.id, e)
                s.rollback()
                raise HTTPException(400, "The PayPal payment could not be completed, so nothing was changed")

            out = {
                "ok": True,
                "trip_id": trip.id,
                "booking_id": booking.id,
                "amount": booking.amount,
                "payment_id": payment.id,
                "payment_status": payment.status,
                "label": booking.label,
            }
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


# ------------------------------------------------------------------ payments (PayPal sandbox)
def payment_dict(p: Payment) -> dict:
    return dict(id=p.id, booking_id=p.booking_id, trip_id=p.trip_id, status=p.status,
                amount_inr=p.amount_inr, amount_usd=p.amount_usd, order_id=p.order_id,
                approve_url=p.approve_url if p.status == "CREATED" else None)


def _pay(fn, *args):
    """Run one payment step. The real reason goes to the server log, never to the browser."""
    try:
        with session_scope() as s:
            return payment_dict(fn(s, *args))
    except PayPalError as e:
        log.warning("PayPal step failed: %s", e)
        raise HTTPException(400, "Payment could not be completed. Please try again.")


class PayStartIn(BaseModel):
    booking_id: str = Field(min_length=1, max_length=30)


class PayOrderIn(BaseModel):
    order_id: str = Field(min_length=8, max_length=40, pattern=r"^[A-Za-z0-9\-]+$")


@app.post("/api/payments/start")
def pay_start(body: PayStartIn):
    return _pay(payments.start_payment, body.booking_id)


@app.post("/api/payments/authorize-by-order")
def pay_authorize_by_order(body: PayOrderIn):
    """The PayPal return page only knows the order id (the token in the URL)."""
    with session_scope() as s:
        p = s.scalar(select(Payment).where(Payment.order_id == body.order_id))
        if p is None:
            raise HTTPException(404, "Unknown payment")
        pid = p.id
    return _pay(payments.authorize, pid)


@app.post("/api/payments/{payment_id}/capture")
def pay_capture(payment_id: int):
    return _pay(payments.capture, payment_id)


@app.get("/api/payments/by-booking/{booking_id}")
def pay_for_booking(booking_id: str):
    with session_scope() as s:
        rows = s.scalars(select(Payment).where(Payment.booking_id == booking_id).order_by(Payment.id)).all()
        return [payment_dict(p) for p in rows]

@app.post("/api/members/{member_id}/paypal/setup")
def paypal_setup(member_id: str):
    try:
        with session_scope() as s:
            return payments.start_vault_setup(s, member_id)
    except PayPalError as e:
        log.warning("PayPal setup failed: %s", e)
        raise HTTPException(400, "Could not start PayPal setup. Please try again.")

class PaySetupDoneIn(BaseModel):
    setup_id: str = Field(min_length=8, max_length=40, pattern=r"^[A-Za-z0-9\-]+$")


@app.post("/api/members/{member_id}/paypal/complete")
def paypal_complete(member_id: str, body: PaySetupDoneIn):
    try:
        with session_scope() as s:
            return payments.complete_vault_setup(s, member_id, body.setup_id)
    except PayPalError as e:
        log.warning("PayPal complete failed: %s", e)
        raise HTTPException(400, "Could not save PayPal. Please try again.")

@app.get("/api/members/{member_id}/paypal")
def paypal_status(member_id: str):
    """Is PayPal saved for this member? Never returns the token itself."""
    with session_scope() as s:
        if s.get(Member, member_id) is None:
            raise HTTPException(404, "Unknown member")
        return {"saved": payments.has_saved_paypal(s, member_id)}

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    hub.sockets.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive; the UI never needs to send
    except WebSocketDisconnect:
        hub.sockets.discard(websocket)
"""Stand-alone disruption simulator.

Pushes events straight onto Azure Event Hubs, exactly like a real airline/rail feed would, so the
backend consumes them live. Run it in a second terminal while the backend and UI are open:

    python simulator.py list
    python simulator.py flight_auto
    python simulator.py stream          # a random scenario every few seconds

It talks to the *database* only to pick a live booking id; the event itself goes over the bus.
Note: without EVENTHUB_CONNECTION_STRING this would use a private in-process queue the backend
cannot see, so the simulator refuses to run — use the UI buttons for offline mode instead.
"""
import asyncio
import random
import sys

from app import config
from app.bus import EventHubBus
from app.db import init_db, session_scope
from app.scenarios import SCENARIOS, build_event


async def send(bus: EventHubBus, scenario_id: str) -> None:
    with session_scope() as s:
        event = build_event(s, scenario_id)
    if event is None:
        print(f"[skip] {scenario_id}: booking already rebooked (reset the demo from the UI)")
        return
    await bus.publish(event)
    print(f"[sent] {scenario_id} -> event {event['event_id']} ({event['type']} on {event['booking_id']})")


async def main(arg: str) -> None:
    if arg == "list":
        for k, v in SCENARIOS.items():
            print(f"{k:18} {v['title']}")
        return
    if not config.USE_EVENTHUB:
        sys.exit("Set EVENTHUB_CONNECTION_STRING in backend/.env first (see azure/README.md).")
    init_db()
    bus = EventHubBus()
    try:
        if arg == "stream":
            while True:
                await send(bus, random.choice(list(SCENARIOS)))
                await asyncio.sleep(random.uniform(4, 8))
        elif arg in SCENARIOS:
            await send(bus, arg)
        else:
            sys.exit(f"Unknown scenario '{arg}'. Try: python simulator.py list")
    finally:
        await bus.close()


if __name__ == "__main__":
    try:
        asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "list"))
    except KeyboardInterrupt:
        pass

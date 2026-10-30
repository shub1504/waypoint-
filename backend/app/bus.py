"""The real-time event bus.

Two interchangeable implementations behind one tiny interface:
  EventHubBus : Azure Event Hubs (used when EVENTHUB_CONNECTION_STRING is set)
  LocalBus    : in-process asyncio queue (zero setup, used for offline development)

Producer (simulator / API)  --publish-->  bus  --consume-->  agent  --WebSocket-->  React
"""
import asyncio
import json
import logging
from typing import Awaitable, Callable

from app import config

log = logging.getLogger("waypoint.bus")
Handler = Callable[[dict], Awaitable[None]]


class LocalBus:
    name = "local"

    def __init__(self) -> None:
        self._q: asyncio.Queue[dict] = asyncio.Queue()

    async def publish(self, event: dict) -> None:
        await self._q.put(event)

    async def consume(self, handler: Handler) -> None:
        while True:
            await handler(await self._q.get())

    async def close(self) -> None:
        pass


class EventHubBus:
    name = "azure-event-hubs"

    def __init__(self) -> None:
        from azure.eventhub.aio import EventHubConsumerClient, EventHubProducerClient

        kw = dict(conn_str=config.EVENTHUB_CONNECTION_STRING, eventhub_name=config.EVENTHUB_NAME)
        self._producer = EventHubProducerClient.from_connection_string(**kw)
        self._consumer = EventHubConsumerClient.from_connection_string(
            consumer_group=config.EVENTHUB_CONSUMER_GROUP, **kw
        )

    async def publish(self, event: dict) -> None:
        from azure.eventhub import EventData

        batch = await self._producer.create_batch()
        batch.add(EventData(json.dumps(event)))
        await self._producer.send_batch(batch)

    async def consume(self, handler: Handler) -> None:
        async def on_event(partition_context, ev):
            if ev is None:
                return
            try:
                await handler(json.loads(ev.body_as_str()))
            except Exception:
                log.exception("failed handling event")

        # "@latest": only events sent after we start — this is the live stream.
        await self._consumer.receive(on_event=on_event, starting_position="@latest")

    async def close(self) -> None:
        await self._producer.close()
        await self._consumer.close()


def make_bus():
    return EventHubBus() if config.USE_EVENTHUB else LocalBus()

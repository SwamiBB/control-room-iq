"""Renderer-facing overlay feed: approved packets and fan cues, in publish order.

Locally, renderers connect to `/ws/overlay`. In Azure the same envelopes also go to the `crq-overlay`
Event Hub, partitioned by match so ordering holds per match.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Literal

from agents.config import settings
from azure.eventhub import EventData
from fastapi import WebSocket
from pydantic import BaseModel

logger = logging.getLogger(__name__)

Envelope = dict
Sink = Callable[[Envelope], Awaitable[None]]


class OverlayFeed:
    def __init__(self) -> None:
        self.renderers: set[WebSocket] = set()
        self.sinks: list[Sink] = []
        self.log: list[Envelope] = []

    async def publish(self, kind: Literal["packet", "fan_cue"], record: BaseModel) -> None:
        envelope = {"type": kind, "match_id": record.match_id, "item": record.model_dump(mode="json")}
        self.log.append(envelope)
        for sink in self.sinks:
            await self._to_sink(sink, envelope)
        for ws in list(self.renderers):
            try:
                await ws.send_json(envelope)
            except Exception:  # noqa: BLE001 - a dropped renderer must not stop the feed
                self.renderers.discard(ws)

    async def _to_sink(self, sink: Sink, envelope: Envelope) -> None:
        try:
            await sink(envelope)
        except Exception:
            # The local feed keeps airing; the failure is visible in logs and App Insights.
            logger.exception("overlay sink failed", extra={"crq.envelope_type": envelope["type"]})


class EventHubsSink:
    def __init__(self, producer) -> None:
        self._producer = producer

    async def __call__(self, envelope: Envelope) -> None:
        batch = await self._producer.create_batch(partition_key=envelope["match_id"])
        batch.add(EventData(json.dumps(envelope)))
        await self._producer.send_batch(batch)

    async def close(self) -> None:
        await self._producer.close()


def eventhubs_sink_from_env() -> EventHubsSink | None:
    """Entra ID auth via DefaultAzureCredential; no keys. None when offline or not configured."""
    namespace = os.environ.get("EVENTHUB_NAMESPACE", "")
    if settings.offline or not namespace:
        return None
    from azure.eventhub.aio import EventHubProducerClient
    from azure.identity.aio import DefaultAzureCredential

    producer = EventHubProducerClient(fully_qualified_namespace=namespace,
                                      eventhub_name=os.environ.get("EVENTHUB_OVERLAY", "crq-overlay"),
                                      credential=DefaultAzureCredential())
    return EventHubsSink(producer)

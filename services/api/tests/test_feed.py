"""The renderer-facing overlay feed and its Event Hubs sink."""

import asyncio
import json
import logging

from api.feed import EventHubsSink, OverlayFeed
from api.main import app, hub
from api_factories import RecordingSocket, proposal
from crq_schemas import FanCue
from fastapi.testclient import TestClient


class FakeBatch:
    def __init__(self) -> None:
        self.bodies: list[str] = []

    def add(self, event) -> None:
        self.bodies.append(event.body_as_str())


class FakeProducer:
    """Stands in for azure.eventhub.aio.EventHubProducerClient."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, list[str]]] = []

    async def create_batch(self, partition_key: str) -> FakeBatch:
        self._key = partition_key
        return FakeBatch()

    async def send_batch(self, batch: FakeBatch) -> None:
        self.sent.append((self._key, batch.bodies))


def _cue() -> FanCue:
    return FanCue(cue_id="fc-1", match_id="m-7", moment_id="mo-1", play_ms=1_000, kind="chance")


def test_feed_sends_typed_envelopes_to_renderers_and_keeps_a_log():
    feed, renderer = OverlayFeed(), RecordingSocket()
    feed.renderers.add(renderer)
    asyncio.run(feed.publish("fan_cue", _cue()))
    (envelope,) = renderer.sent
    assert envelope == {"type": "fan_cue", "match_id": "m-7", "item": _cue().model_dump(mode="json")}
    assert feed.log == [envelope]


def test_feed_logs_a_failing_sink_and_still_reaches_renderers(caplog):
    async def broken_sink(_envelope):
        raise ConnectionError("hub unreachable")

    feed, renderer = OverlayFeed(), RecordingSocket()
    feed.sinks.append(broken_sink)
    feed.renderers.add(renderer)
    with caplog.at_level(logging.ERROR):
        asyncio.run(feed.publish("fan_cue", _cue()))
    assert len(renderer.sent) == 1
    assert "overlay sink failed" in caplog.text


def test_eventhubs_sink_partitions_by_match():
    producer = FakeProducer()
    envelope = {"type": "fan_cue", "match_id": "m-7", "item": {}}
    asyncio.run(EventHubsSink(producer)(envelope))
    assert producer.sent == [("m-7", [json.dumps(envelope)])]


def test_approved_packet_is_published_to_the_feed():
    p = proposal()
    hub.proposals[p.proposal_id] = p
    TestClient(app).post(f"/proposals/{p.proposal_id}/approve")
    (envelope,) = hub.feed.log
    assert envelope["type"] == "packet" and envelope["item"]["source_proposal_id"] == p.proposal_id

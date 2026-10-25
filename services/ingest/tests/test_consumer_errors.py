"""The Event Hubs consumer logs what it can't read instead of failing silently (#63). Azure clients are faked."""

import asyncio
import json
import logging

from azure.core.exceptions import ResourceNotFoundError
from ingest.consumer import IDLE_WARN_S, make_handlers
from simulator.cli import MatchEngine, build_meta


class FakeContainer:
    def __init__(self):
        self.items = {}

    async def upsert_item(self, item):
        self.items[item["id"]] = item

    async def read_item(self, item_id, partition_key):
        if item_id not in self.items:
            raise ResourceNotFoundError("not found")
        return self.items[item_id]


class FakeEvent:
    def __init__(self, body, offset):
        self.body, self.offset = body, str(offset)

    def body_as_str(self):
        return self.body


class FakePartition:
    partition_id = "3"

    def __init__(self):
        self.checkpoints = []

    async def update_checkpoint(self, event):
        self.checkpoints.append(event.offset)


def _run(records, caplog):
    matches, moments, state = FakeContainer(), FakeContainer(), FakeContainer()
    published = []

    async def publish(m):
        published.append(m)

    on_event, _ = make_handlers(matches, moments, state, publish)
    part = FakePartition()

    async def go():
        for i, body in enumerate(records):
            await on_event(part, FakeEvent(body, i))

    with caplog.at_level(logging.WARNING, logger="ingest.consumer"):
        asyncio.run(go())
    return part, matches, published


def _match():
    meta = build_meta(5)
    return meta, [e.model_dump_json() for e in MatchEngine(meta).run()]


def test_bad_records_are_logged_with_partition_and_offset_and_checkpointed_past(caplog):
    meta, events = _match()
    records = [json.dumps({"probe": "access-check"}), "not json", "[1, 2]", meta.model_dump_json(), *events]
    part, matches, published = _run(records, caplog)

    skipped = [r.getMessage() for r in caplog.records if "skipped record" in r.getMessage()]
    assert len(skipped) == 3
    assert all("partition 3" in s for s in skipped)
    assert "offset 0" in skipped[0] and "ValidationError" in skipped[0]
    assert part.checkpoints == [str(i) for i in range(len(records))], "the bad records don't stall the partition"
    assert meta.match_id in matches.items and published, "the match after them is still folded"


def test_an_event_for_an_unseen_match_says_its_meta_is_missing(caplog):
    meta, events = _match()
    part, _, published = _run(events[:5], caplog)
    msgs = [r.getMessage() for r in caplog.records]
    assert len(msgs) == 5 and all(f"no MatchMeta record for match {meta.match_id}" in m for m in msgs)
    assert len(part.checkpoints) == 5 and not published


def test_silence_is_logged_once_until_the_next_event(caplog):
    meta, _ = _match()
    on_event, on_error = make_handlers(FakeContainer(), FakeContainer(), FakeContainer(), None)
    part = FakePartition()

    async def go():
        for _ in range(8):  # every idle partition reports in
            await on_event(part, None)
        await on_event(part, FakeEvent(meta.model_dump_json(), 0))
        await on_event(part, None)
        await on_error(part, PermissionError("unauthorized"))

    with caplog.at_level(logging.WARNING, logger="ingest.consumer"):
        asyncio.run(go())
    msgs = [r.getMessage() for r in caplog.records]
    idle = [m for m in msgs if f"no events read in {IDLE_WARN_S} s" in m]
    assert len(idle) == 2 and "Data Receiver" in idle[0]
    assert msgs[-1] == "Event Hubs error on partition 3: PermissionError: unauthorized"

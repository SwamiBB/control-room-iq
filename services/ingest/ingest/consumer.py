"""Event Hubs consumer for the ingest service (runs on Azure Container Apps, KEDA-scaled).

Reads `crq-events`, folds into MatchState, writes state snapshots and moments to Cosmos DB, and
publishes moments to `crq-moments` for the agents runner. Local mode (`python -m ingest.consumer
--file data/match.jsonl`) does the same fold without Azure and prints moments.

Failures are logged, not silent: a record ingest can't use (not JSON, not a MatchEvent or MatchMeta, or an
event for a match it has never seen) is logged with its partition and offset and checkpointed past, so it never
stalls a partition. Event Hubs errors are logged through on_error. Reading without the Data Receiver role raises
no error at all, so a long silence is logged too, naming both causes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

from crq_schemas import MatchEvent, MatchMeta

from .stats import StateFolder

log = logging.getLogger("ingest.consumer")
IDLE_WARN_S = 60  # no event on any partition for this long is logged once, until the next event


class UnusableRecord(Exception):
    """A record ingest can't fold; logged and skipped."""


def fold_file(path: Path):
    with path.open(encoding="utf-8") as f:
        meta = MatchMeta.model_validate_json(f.readline())
        folder = StateFolder(meta)
        for line in f:
            if line.strip():
                yield from folder.apply(MatchEvent.model_validate_json(line))
    return folder


async def run_eventhub() -> None:
    from azure.cosmos.aio import CosmosClient
    from azure.eventhub import EventData
    from azure.eventhub.aio import EventHubConsumerClient, EventHubProducerClient
    from azure.identity.aio import DefaultAzureCredential

    cred = DefaultAzureCredential()
    ns = os.environ["EVENTHUB_NAMESPACE"]
    consumer = EventHubConsumerClient(fully_qualified_namespace=ns,
                                      eventhub_name=os.environ.get("EVENTHUB_EVENTS", "crq-events"),
                                      consumer_group=os.environ.get("EVENTHUB_CONSUMER_GROUP", "$Default"),
                                      credential=cred)
    producer = EventHubProducerClient(fully_qualified_namespace=ns,
                                      eventhub_name=os.environ.get("EVENTHUB_MOMENTS", "crq-moments"), credential=cred)
    cosmos = CosmosClient(os.environ["COSMOS_ENDPOINT"], credential=cred)
    db = cosmos.get_database_client(os.environ.get("COSMOS_DB", "crq"))
    moments_c, state_c, matches_c = (db.get_container_client("moments"), db.get_container_client("state"),
                                     db.get_container_client("matches"))

    async def publish(m) -> None:
        async with producer:
            batch = await producer.create_batch(partition_key=m.match_id)
            batch.add(EventData(m.model_dump_json()))
            await producer.send_batch(batch)

    on_event, on_error = make_handlers(matches_c, moments_c, state_c, publish)
    log.info("reading %s from %s", consumer.eventhub_name, ns)
    async with consumer:
        await consumer.receive(on_event=on_event, on_error=on_error, starting_position="-1",
                               max_wait_time=IDLE_WARN_S)


def make_handlers(matches_c, moments_c, state_c, publish, clock=time.monotonic):
    """on_event and on_error for EventHubConsumerClient.receive. The Azure clients are passed in, so tests can
    fake them."""
    from azure.core.exceptions import ResourceNotFoundError

    folders: dict[str, StateFolder] = {}
    idle = {"last": clock(), "warned": False}  # one clock for the consumer: a match keeps only one partition busy

    async def fold(body: dict) -> None:
        if "home" in body:  # MatchMeta record
            meta = MatchMeta.model_validate(body)
            folders[meta.match_id] = StateFolder(meta)
            await matches_c.upsert_item({**body, "id": meta.match_id})
            return
        ev = MatchEvent.model_validate(body)
        folder = folders.get(ev.match_id)
        if folder is None:
            try:
                item = await matches_c.read_item(ev.match_id, partition_key=ev.match_id)
            except ResourceNotFoundError:
                raise UnusableRecord(f"no MatchMeta record for match {ev.match_id}; it must be sent first") from None
            folder = folders[ev.match_id] = StateFolder(MatchMeta.model_validate(item))
        for m in folder.apply(ev):
            await moments_c.upsert_item({**json.loads(m.model_dump_json()), "id": m.moment_id})
            await publish(m)
        if ev.seq % 25 == 0:
            snapshot = {**json.loads(folder.state.model_dump_json()), "id": f"{ev.match_id}-{ev.seq}"}
            await state_c.upsert_item(snapshot)

    async def on_event(partition_context, event) -> None:
        if event is None:  # nothing on this partition for IDLE_WARN_S; warn only if no partition has had anything
            if not idle["warned"] and clock() - idle["last"] >= IDLE_WARN_S:
                idle["warned"] = True
                log.warning("no events read in %d s: either nothing is being sent, or this identity lacks the "
                            "Azure Event Hubs Data Receiver role (reading without it returns nothing, no error)",
                            IDLE_WARN_S)
            return
        idle["last"], idle["warned"] = clock(), False
        try:
            body = json.loads(event.body_as_str())
            if not isinstance(body, dict):
                raise UnusableRecord("not a JSON object")
            await fold(body)
        except (ValueError, UnusableRecord) as exc:  # bad JSON and pydantic ValidationError are ValueErrors
            reason = " ".join(str(exc).splitlines()[:3])  # a ValidationError's first field errors, not all of them
            if not isinstance(exc, UnusableRecord):
                reason = f"{type(exc).__name__}: {reason}"
            log.warning("skipped record on partition %s at offset %s: %s", partition_context.partition_id,
                        event.offset, reason[:300])
        await partition_context.update_checkpoint(event)  # past a skipped record too, so it can't stall the partition

    async def on_error(partition_context, error: Exception) -> None:
        log.warning("Event Hubs error on partition %s: %s: %s",
                    partition_context.partition_id if partition_context else "-", type(error).__name__, error)

    return on_event, on_error


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--file", help="local JSONL match file; omit to consume from Event Hubs")
    a = p.parse_args(argv)
    if a.file:
        n = 0
        for m in fold_file(Path(a.file)):
            n += 1
            print(f"[{m.period}H {m.t_ms // 60000:02d}'] {m.kind.value:15s} {m.importance:.2f}  {m.summary}")
        print(f"{n} moments", file=sys.stderr)
    else:
        logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        log.setLevel(logging.INFO)
        asyncio.run(run_eventhub())


if __name__ == "__main__":
    main()

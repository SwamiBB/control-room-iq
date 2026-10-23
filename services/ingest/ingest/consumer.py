"""Event Hubs consumer for the ingest service (runs on Azure Container Apps, KEDA-scaled).

Reads `crq-events`, folds into MatchState, writes state snapshots and moments to Cosmos DB, and
publishes moments to `crq-moments` for the agents runner. Local mode (`python -m ingest.consumer
--file data/match.jsonl`) does the same fold without Azure and prints moments.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from crq_schemas import MatchEvent, MatchMeta

from .stats import StateFolder


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
    folders: dict[str, StateFolder] = {}

    async def on_event(partition_context, event: EventData | None):
        if event is None:
            return
        body = json.loads(event.body_as_str())
        if "home" in body:  # MatchMeta record
            meta = MatchMeta.model_validate(body)
            folders[meta.match_id] = StateFolder(meta)
            await matches_c.upsert_item({**body, "id": meta.match_id})
        else:
            ev = MatchEvent.model_validate(body)
            folder = folders.get(ev.match_id)
            if folder is None:
                item = await matches_c.read_item(ev.match_id, partition_key=ev.match_id)
                folder = folders[ev.match_id] = StateFolder(MatchMeta.model_validate(item))
            for m in folder.apply(ev):
                await moments_c.upsert_item({**json.loads(m.model_dump_json()), "id": m.moment_id})
                async with producer:
                    batch = await producer.create_batch(partition_key=m.match_id)
                    batch.add(EventData(m.model_dump_json()))
                    await producer.send_batch(batch)
            if ev.seq % 25 == 0:
                snapshot = {**json.loads(folder.state.model_dump_json()), "id": f"{ev.match_id}-{ev.seq}"}
                await state_c.upsert_item(snapshot)
        await partition_context.update_checkpoint(event)

    async with consumer:
        await consumer.receive(on_event=on_event, starting_position="-1")


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
        asyncio.run(run_eventhub())


if __name__ == "__main__":
    main()

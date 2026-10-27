"""The decision log, persisted: every decision is appended to Cosmos DB's `decisions` container, per run.

The in-memory log (`hub.decisions`) stays the operator's live view of the current run; this is the durable copy
behind it, so the audit trail survives a new run ("Run again") and an API restart. Each document is one decision,
written once (`create_item`), tagged with the run it belongs to and its place in that run.

Writes run in one background task, in order, so a fire never waits on Cosmos DB and a Cosmos DB failure never fails
a fire: the SDK retries, then the failure is logged. Off when offline or COSMOS_ENDPOINT is unset (tests, laptops),
which leaves the API exactly as it was. Entra ID only, with the workload's managed identity; no keys.
"""

from __future__ import annotations

import asyncio
import logging
import os

from agents.config import settings
from crq_schemas import DecisionLogEntry

logger = logging.getLogger(__name__)

CONTAINER = "decisions"  # partition key /match_id (infra/modules/data.bicep)
MAX_PENDING = 10_000  # decisions waiting to be written; beyond this, Cosmos DB is down and they are logged and dropped
CLOSE_WAIT_S = 5.0


class DecisionStore:
    def __init__(self, container, client=None, credential=None) -> None:
        self._container = container
        self._client, self._credential = client, credential
        self._queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=MAX_PENDING)
        self._worker: asyncio.Task | None = None

    def start(self) -> None:
        """Start the writer; call from the running event loop (the API's lifespan)."""
        self._worker = asyncio.create_task(self._drain())

    def add(self, entry: DecisionLogEntry, run_id: str, seq: int) -> None:
        """Queue one decision for writing. Never blocks and never raises: the decision has already been made."""
        doc = entry.model_dump(mode="json") | {"id": f"{run_id}-{entry.entry_id}", "run_id": run_id, "seq": seq}
        try:
            self._queue.put_nowait(doc)
        except asyncio.QueueFull:
            logger.error("decision %s not persisted: %d already waiting for Cosmos DB", doc["id"], MAX_PENDING)

    async def _drain(self) -> None:
        while True:
            doc = await self._queue.get()
            try:
                await self._container.create_item(doc)
            except Exception:  # noqa: BLE001 - the decision stands; the gap is visible in the logs
                logger.exception("decision %s not persisted to Cosmos DB", doc["id"])
            finally:
                self._queue.task_done()

    async def history(self, run_id: str | None = None) -> list[dict]:
        """Every persisted decision, or one run's, in the order they were made. Cross-partition: the volume is small.
        Sorted here rather than in the query, which would need a composite index for two keys."""
        query, params = "SELECT * FROM c", []
        if run_id:
            query, params = "SELECT * FROM c WHERE c.run_id = @run", [{"name": "@run", "value": run_id}]
        # No enable_cross_partition_query: the async client queries across partitions by default and passes that
        # keyword on to the HTTP session, which rejects it (found by the live check against Cosmos DB).
        docs = [d async for d in self._container.query_items(query=query, parameters=params)]
        return sorted(docs, key=lambda d: (d.get("at", ""), d.get("run_id", ""), d.get("seq", 0)))

    async def close(self) -> None:
        """Write what is queued (briefly), then release the client."""
        try:
            await asyncio.wait_for(self._queue.join(), CLOSE_WAIT_S)
        except TimeoutError:
            logger.warning("%d decisions not persisted at shutdown", self._queue.qsize())
        if self._worker:
            self._worker.cancel()
        if self._client:
            await self._client.close()
        if self._credential:
            await self._credential.close()


def decision_store_from_env() -> DecisionStore | None:
    """None when offline or Cosmos DB isn't configured; the in-memory log then works alone, as before."""
    endpoint = os.environ.get("COSMOS_ENDPOINT", "")
    if settings.offline or not endpoint:
        return None
    from azure.cosmos.aio import CosmosClient
    from azure.identity.aio import DefaultAzureCredential

    credential = DefaultAzureCredential()
    client = CosmosClient(endpoint, credential=credential)
    container = client.get_database_client(os.environ.get("COSMOS_DB", "crq")).get_container_client(CONTAINER)
    return DecisionStore(container, client=client, credential=credential)

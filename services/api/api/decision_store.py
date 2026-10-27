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
import contextlib
import logging
import os
from datetime import UTC, datetime

from agents.config import settings
from crq_schemas import DecisionLogEntry

logger = logging.getLogger(__name__)

CONTAINER = "decisions"  # partition key /match_id (infra/modules/data.bicep)
MAX_PENDING = 10_000  # decisions waiting to be written; beyond this, Cosmos DB is down and they are logged and dropped
CLOSE_WAIT_S = 5.0
MAX_HISTORY = 5_000  # newest decisions returned by one history read; each read is a cross-partition query


class DecisionStore:
    def __init__(self, container, client=None, credential=None) -> None:
        self._container = container
        self._client, self._credential = client, credential
        self._queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=MAX_PENDING)
        self._worker: asyncio.Task | None = None
        self._closed = False

    def start(self) -> None:
        """Start the writer; call from the running event loop (the API's lifespan)."""
        self._worker = asyncio.create_task(self._drain())

    def add(self, entry: DecisionLogEntry, run_id: str, seq: int) -> None:
        """Queue one decision for writing. Never blocks and never raises: the decision has already been made."""
        doc = entry.model_dump(mode="json") | {"id": f"{run_id}-{entry.entry_id}", "run_id": run_id, "seq": seq}
        if self._closed:
            logger.error("decision %s not persisted: the API is shutting down", doc["id"])
            return
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
        """The newest MAX_HISTORY persisted decisions, or one run's, in the order they were made: within a run by its
        sequence (two decisions can share a timestamp), runs by when they started. Sorted here, since ordering by
        two keys in the query would need a composite index."""
        where = " WHERE c.run_id = @run" if run_id else ""
        query = f"SELECT TOP @limit * FROM c{where} ORDER BY c._ts DESC"
        params = [{"name": "@limit", "value": MAX_HISTORY}] + ([{"name": "@run", "value": run_id}] if run_id else [])
        # No enable_cross_partition_query: the async client queries across partitions by default and passes that
        # keyword on to the HTTP session, which rejects it (found by the live check against Cosmos DB).
        docs = [d async for d in self._container.query_items(query=query, parameters=params)]
        started: dict[str, datetime] = {}
        first_decision: dict[str, datetime] = {}
        for d in docs:
            run_id = d.get("run_id", "")
            at = _when(d)
            first_decision[run_id] = min(at, first_decision.get(run_id, at))
        for run_id, at in first_decision.items():
            try:
                started[run_id] = datetime.strptime(run_id[2:17], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
            except ValueError:
                started[run_id] = at
        return sorted(docs, key=lambda d: (started[d.get("run_id", "")], d.get("run_id", ""), d.get("seq", 0)))

    async def close(self) -> None:
        """Write what is queued (briefly), then release the client."""
        try:
            await asyncio.wait_for(self._queue.join(), CLOSE_WAIT_S)
        except TimeoutError:
            logger.warning("%d decisions not persisted at shutdown", self._queue.qsize())
        self._closed = True
        if self._worker:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker  # no write left half-done when the client closes
        if self._client:
            await self._client.close()
        if self._credential:
            await self._credential.close()


def _when(doc: dict) -> datetime:
    """The decision's time as a datetime: the stored text can't be sorted as text (a whole second has no fraction)."""
    try:
        value = datetime.fromisoformat(doc.get("at", ""))
    except ValueError:
        return datetime.max.replace(tzinfo=UTC)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


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

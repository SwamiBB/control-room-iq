"""The persisted decision log: every decision reaches Cosmos DB once, per run, never delaying or failing a fire."""

import asyncio
import logging

import pytest
from api.decision_store import DecisionStore, decision_store_from_env
from api.main import _auto_hold, app, hub
from api_factories import proposal
from conftest import FIXED_NOW
from crq_schemas import DecisionLogEntry
from fastapi.testclient import TestClient


class Recorder:
    """Stands in for the store on the API side: what _record_decision hands over."""

    def __init__(self) -> None:
        self.added: list[tuple[DecisionLogEntry, str, int]] = []

    def add(self, entry, run_id, seq):
        self.added.append((entry, run_id, seq))


class FakeContainer:
    """Stands in for the Cosmos DB container: create_item and query_items, optionally failing."""

    def __init__(self, fail_ids=()):
        self.items: list[dict] = []
        self.fail_ids = set(fail_ids)

    async def create_item(self, doc):
        if doc["id"] in self.fail_ids:
            raise RuntimeError("503 from Cosmos DB")
        self.items.append(doc)

    def query_items(self, query, parameters):  # the async client's signature: no cross-partition flag
        run = next((p["value"] for p in parameters if p["name"] == "@run"), None)

        async def gen():
            for d in self.items:
                if run is None or d["run_id"] == run:
                    yield d
        return gen()


def _entry(n: int, action="approved") -> DecisionLogEntry:
    return DecisionLogEntry(entry_id=f"d-{n:08x}", match_id="m", proposal_id=f"p-{n}", action=action,
                            actor="operator", at=FIXED_NOW)


def _seed(*ids):
    for pid in ids:
        hub.proposals[pid] = proposal(pid)


# ---------- the API hands every decision to the store ----------

def test_every_decision_is_handed_to_the_store_once_in_order(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(hub, "store", recorder)
    _seed("p-a", "p-b", "p-c")
    client = TestClient(app)
    client.post("/proposals/p-a/approve")
    client.post("/proposals/p-b/hold")
    client.post("/proposals/p-b/approve")  # a held graphic fired later: a second decision on it
    client.post("/proposals/p-c/reject")
    assert [(e.proposal_id, e.action.value, run, seq) for e, run, seq in recorder.added] == [
        ("p-a", "approved", hub.run_id, 1), ("p-b", "held", hub.run_id, 2),
        ("p-b", "approved", hub.run_id, 3), ("p-c", "rejected", hub.run_id, 4)]
    assert [e for e, _, _ in recorder.added] == hub.decisions  # the same entries the console shows


def test_run_again_is_a_new_run_and_restarts_the_count():
    first = hub.run_id
    hub.decision_seq = 7
    from simulator.cli import build_meta

    hub.new_match(build_meta(42))
    assert hub.run_id != first and hub.run_id.startswith("r-") and hub.decision_seq == 0


def test_a_timer_from_the_previous_run_writes_nothing(monkeypatch):
    """After "Run again" the old run's proposal is gone, so its pending 20 s hold records no decision."""
    from simulator.cli import build_meta

    recorder = Recorder()
    monkeypatch.setattr(hub, "store", recorder)
    _seed("p-old")
    hub.auto_hold_s, hub.warn_s = 0, 0

    async def run():
        timer = asyncio.create_task(_auto_hold("p-old"))
        hub.new_match(build_meta(42))
        await timer

    asyncio.run(run())
    assert recorder.added == [] and hub.decisions == []


def test_without_cosmos_db_there_is_no_store(monkeypatch):
    monkeypatch.delenv("COSMOS_ENDPOINT", raising=False)
    assert decision_store_from_env() is None
    monkeypatch.setenv("COSMOS_ENDPOINT", "https://example.documents.azure.com:443/")
    assert decision_store_from_env() is None  # the tests run offline, as demos without Azure do


# ---------- the store writes in the background, in order, and survives failures ----------

def test_the_store_writes_each_decision_once_in_order_with_its_run():
    container = FakeContainer()

    async def run():
        store = DecisionStore(container)
        store.start()
        for n in (1, 2, 3):
            store.add(_entry(n), "r-1", n)
        await store.close()

    asyncio.run(run())
    assert [(d["id"], d["run_id"], d["seq"], d["action"]) for d in container.items] == [
        ("r-1-d-00000001", "r-1", 1, "approved"), ("r-1-d-00000002", "r-1", 2, "approved"),
        ("r-1-d-00000003", "r-1", 3, "approved")]
    assert container.items[0]["match_id"] == "m" and container.items[0]["at"].startswith("2026-10-23")


def test_a_failed_write_is_logged_and_the_rest_still_go_through(caplog):
    container = FakeContainer(fail_ids={"r-1-d-00000002"})

    async def run():
        store = DecisionStore(container)
        store.start()
        for n in (1, 2, 3):
            store.add(_entry(n), "r-1", n)
        await store.close()

    with caplog.at_level(logging.ERROR, logger="api.decision_store"):
        asyncio.run(run())
    assert [d["seq"] for d in container.items] == [1, 3]
    assert "r-1-d-00000002 not persisted" in caplog.text


def test_add_never_blocks_or_raises_when_cosmos_db_is_backed_up(monkeypatch, caplog):
    import api.decision_store as ds

    monkeypatch.setattr(ds, "MAX_PENDING", 1)

    async def run():
        store = DecisionStore(FakeContainer())  # not started: nothing drains
        store.add(_entry(1), "r-1", 1)
        store.add(_entry(2), "r-1", 2)  # full: logged and dropped, the caller carries on

    with caplog.at_level(logging.ERROR, logger="api.decision_store"):
        asyncio.run(run())
    assert "r-1-d-00000002 not persisted" in caplog.text


def test_history_is_one_run_or_all_runs_in_the_order_decided():
    container = FakeContainer()
    container.items = [
        {**_entry(3).model_dump(mode="json"), "id": "r-2-c", "run_id": "r-2", "seq": 1},
        {**_entry(2).model_dump(mode="json"), "id": "r-1-b", "run_id": "r-1", "seq": 2},
        {**_entry(1).model_dump(mode="json"), "id": "r-1-a", "run_id": "r-1", "seq": 1},
    ]
    store = DecisionStore(container)
    assert [d["id"] for d in asyncio.run(store.history("r-1"))] == ["r-1-a", "r-1-b"]
    assert [d["id"] for d in asyncio.run(store.history())] == ["r-1-a", "r-1-b", "r-2-c"]


# ---------- /decisions.csv ----------

def test_the_current_run_csv_is_unchanged_and_names_its_run():
    hub.decisions.append(_entry(1))
    res = TestClient(app).get("/decisions.csv")
    assert res.status_code == 200 and res.headers["x-crq-run-id"] == hub.run_id
    assert res.text.splitlines()[0] == "entry_id,match_id,proposal_id,action,actor,at,reasoning,package_id"


def test_the_persisted_log_needs_cosmos_db():
    res = TestClient(app).get("/decisions.csv?run=all")
    assert res.status_code == 503


def test_the_persisted_log_as_csv_with_its_runs(monkeypatch):
    container = FakeContainer()
    container.items = [{**_entry(1).model_dump(mode="json"), "id": "r-1-a", "run_id": "r-1", "seq": 1},
                       {**_entry(2).model_dump(mode="json"), "id": "r-2-a", "run_id": "r-2", "seq": 1}]
    monkeypatch.setattr(hub, "store", DecisionStore(container))
    client = TestClient(app)
    rows = client.get("/decisions.csv?run=all").text.splitlines()
    assert rows[0].endswith(",run_id,seq") and [r.split(",")[-2] for r in rows[1:]] == ["r-1", "r-2"]
    one = client.get("/decisions.csv?run=r-2")
    assert len(one.text.splitlines()) == 2 and "decisions-r-2.csv" in one.headers["content-disposition"]


@pytest.mark.parametrize("bad", ["", "r-1;drop", "../etc", "R" * 50])
def test_a_run_that_is_not_a_run_id_is_refused(bad):
    assert TestClient(app).get(f"/decisions.csv?run={bad}").status_code == 422

import os

os.environ["CRQ_OFFLINE"] = "1"

import asyncio  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import api.main as api  # noqa: E402
from api import evaluation  # noqa: E402
from api.offline import replay_offline  # noqa: E402
from simulator.cli import write_match  # noqa: E402
from simulator.scripted import DATA_DIR, generate  # noqa: E402


def test_one_row_per_agent_output_over_the_reference_match(tmp_path):
    meta, events = generate(DATA_DIR / "storyline.json")
    path = tmp_path / "match.jsonl"
    write_match(path, meta, events)
    records = []
    rows = asyncio.run(replay_offline(path, records=records))
    sent = [r for r in rows if r.moment.importance >= 0.3]
    variants = len(records) - sum(r.agent != "personalizer" for r in records)
    expected = sum(2 + (1 if r.proposal else 0) for r in sent) + variants
    assert len(records) == expected
    assert {r.agent for r in records} == {"explainer", "narrator", "personalizer", "producer"}
    assert all(r.cites and r.source == "template" and r.latency_ms >= 0 for r in records)
    assert {r.lang for r in records if r.agent == "personalizer"} >= {"en", "es", "hi"}
    hero = [r for r in records if r.agent == "producer" and "xG 0.38" in r.output]
    assert hero and hero[0].snapshot["hold_advice"]["recommend"] == "hold"

    lines = [json.loads(x) for x in evaluation.to_foundry_jsonl(records).splitlines()]
    assert len(lines) == len(records)
    assert all({"query", "context", "response", "id"} <= set(x) for x in lines)


def test_operator_edit_lands_on_the_producer_row_only():
    with TestClient(api.app) as c:
        c.get("/api/replay", params={"seed": 42, "speed": 1})
        c.post("/api/replay/jump", params={"minute": 41, "second": 12})
        c.post("/api/replay/speed", params={"x": 8})
        deadline = time.monotonic() + 10
        goal = None
        while time.monotonic() < deadline and goal is None:
            time.sleep(0.1)
            goal = next((p for p in api.hub.proposals.values() if p.line.startswith("GOAL Finn Oakes")), None)
        c.post(f"/proposals/{goal.proposal_id}/override", json={"actor": "op", "override_line": "GOAL! Oakes!"})
        api.replay_session.task.cancel()
        rows = [r for r in c.get("/api/evaluations").json() if r["moment_id"] == goal.moment_id]
        assert {r["agent"] for r in rows} >= {"explainer", "narrator", "producer"}
        assert all(r["decision_id"] for r in rows)
        assert [r["edited_line"] for r in rows if r["agent"] == "producer"] == ["GOAL! Oakes!"]
        assert not [r for r in rows if r["agent"] != "producer" and r["edited_line"]]
        jsonl = c.get("/api/evaluations.jsonl").text.splitlines()
        assert any(json.loads(x)["response"] == "GOAL! Oakes!" for x in jsonl)

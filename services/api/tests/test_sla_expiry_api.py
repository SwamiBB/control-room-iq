"""The console is warned before the SLA hold; held graphics expire once the match moves on."""

import asyncio

from api.main import _auto_hold, _expire_stale, _queue_proposal, app, hub
from api.timing import MIN_SHELF_LIFE_MS
from api_factories import RecordingSocket, proposal
from crq_schemas import ProposalStatus
from fastapi.testclient import TestClient


def _console() -> RecordingSocket:
    ws = RecordingSocket()
    hub.operators.add(ws)
    return ws


def _held(pid: str = "p-1", proposed_play_ms: int = 600_000, **overrides) -> str:
    p = proposal(pid, **({"status": ProposalStatus.HELD, "proposed_play_ms": proposed_play_ms} | overrides))
    hub.proposals[pid] = p
    hub.results[p.moment_id] = {"variants": [], "fan_card": None}
    return pid


def test_queued_proposals_carry_their_warning_and_hold_times():
    hub.clock.play_ms = 600_000
    hub.auto_hold_s = 3600  # keep the background timer out of the test
    asyncio.run(_queue_proposal(proposal()))
    p = hub.proposals["p-1"]
    assert p.proposed_at == hub.now() and p.proposed_play_ms == 600_000
    assert (p.warn_at - p.proposed_at).total_seconds() == 3590 and (p.hold_at - p.proposed_at).total_seconds() == 3600


def test_console_is_warned_before_the_hold():
    console = _console()
    hub.auto_hold_s, hub.warn_s = 0, 0
    hub.proposals["p-1"] = proposal()
    asyncio.run(_auto_hold("p-1"))
    (warning,) = console.of_type("sla_warning")
    assert warning["proposal_id"] == "p-1" and warning["seconds_left"] == 0
    assert hub.proposals["p-1"].status == ProposalStatus.HELD


def test_no_warning_once_the_operator_has_decided():
    console = _console()
    hub.auto_hold_s, hub.warn_s = 0, 0
    hub.proposals["p-1"] = proposal(status=ProposalStatus.REJECTED)
    asyncio.run(_auto_hold("p-1"))
    assert console.of_type("sla_warning") == []


def test_a_stale_held_graphic_expires_with_a_log_row():
    console = _console()
    pid = _held()
    hub.clock.play_ms = 600_000 + MIN_SHELF_LIFE_MS + 1
    asyncio.run(_expire_stale())
    assert hub.proposals[pid].status == ProposalStatus.EXPIRED
    assert (hub.decisions[-1].actor, hub.decisions[-1].action) == ("expiry-rule", "expired")
    assert console.of_type("proposal")[-1]["proposal"]["status"] == "expired"


def test_an_expired_graphic_cannot_be_fired_late():
    pid = _held()
    hub.clock.play_ms = 600_000 + MIN_SHELF_LIFE_MS + 1
    r = TestClient(app).post(f"/proposals/{pid}/approve")
    assert r.status_code == 409 and hub.packets == []
    assert hub.proposals[pid].status == ProposalStatus.EXPIRED


def test_a_held_graphic_can_still_be_fired_within_its_shelf_life():
    pid = _held()
    hub.clock.play_ms = 600_000 + MIN_SHELF_LIFE_MS
    assert TestClient(app).post(f"/proposals/{pid}/approve").status_code == 200
    assert len(hub.packets) == 1


def test_the_expiry_rule_cannot_air_anything():
    pid = _held()
    for action in ("approve", "reject"):
        r = TestClient(app).post(f"/proposals/{pid}/{action}", json={"actor": "expiry-rule"})
        assert r.status_code == 403
    assert hub.packets == []


def test_metrics_count_expiries_apart_from_operator_decisions():
    _held()
    hub.clock.play_ms = 600_000 + MIN_SHELF_LIFE_MS + 1
    asyncio.run(_expire_stale())
    w = TestClient(app).get("/metrics").json()["workload"]
    assert (w["expired"], w["operator_decisions"]) == (1, 0)

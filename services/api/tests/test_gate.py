import os

os.environ["CRQ_OFFLINE"] = "1"

import csv  # noqa: E402
import io  # noqa: E402
import time  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api.main as api  # noqa: E402
from api import gate  # noqa: E402
from crq_schemas import OverlayLayer, OverlayProposal, ProposalStatus as S  # noqa: E402

TERMINAL = [S.APPROVED, S.OVERRIDDEN, S.SUPERSEDED, S.AIRED, S.EXPIRED]


@pytest.mark.parametrize("status", list(S))
def test_only_an_operator_can_air_anything(status):
    for actor in ("sla", "supersession"):
        for action in ("approve", "override"):
            with pytest.raises(gate.IllegalTransition):
                gate.next_status(status, action, actor)


@pytest.mark.parametrize("status", TERMINAL)
def test_decided_proposals_accept_nothing(status):
    for action, actor in gate.ACTOR.items():
        with pytest.raises(gate.IllegalTransition):
            gate.next_status(status, action, actor)


def test_legal_paths():
    assert gate.next_status(S.PROPOSED, "approve", "operator") == S.APPROVED
    assert gate.next_status(S.PROPOSED, "sla_hold", "sla") == S.SLA_HELD
    assert gate.next_status(S.SLA_HELD, "approve", "operator") == S.APPROVED  # the operator can still air it
    assert gate.next_status(S.HELD, "supersede", "supersession") == S.SUPERSEDED
    with pytest.raises(gate.IllegalTransition):
        gate.next_status(S.HELD, "sla_hold", "sla")  # the SLA only acts on untouched proposals


def _seed(pid, line="A line"):
    api.hub.proposals[pid] = OverlayProposal(proposal_id=pid, match_id="m", moment_id="mo-" + pid,
                                             layer=OverlayLayer.LOWER_THIRD, t_start_ms=1000, t_end_ms=9000, line=line,
                                             reasoning="r", priority=0.7)
    return pid


def _rows(c):
    return list(csv.DictReader(io.StringIO(c.get("/api/decisions.csv").text)))


def test_sla_auto_hold_is_a_logged_decision_and_any_operator_action_cancels_it():
    with TestClient(api.app) as c:
        api.hub.auto_hold_s = 0.05
        try:
            c.portal.call(api._auto_hold, _seed("p-sla"))
            assert api.hub.proposals["p-sla"].status == S.SLA_HELD
            _seed("p-touched")
            c.post("/proposals/p-touched/hold", json={"actor": "op"})
            c.portal.call(api._auto_hold, "p-touched")
            assert api.hub.proposals["p-touched"].status == S.HELD, "the operator acted first, so no SLA hold"
        finally:
            api.hub.auto_hold_s = 20.0
        sla = [r for r in _rows(c) if r["proposal_id"] == "p-sla"]
        assert [(r["action"], r["actor"]) for r in sla] == [("sla_hold", "sla")]
        assert c.post("/proposals/p-sla/approve", json={"actor": "op"}).json()["status"] == "aired"


def test_supersession_replaces_pending_lower_priority_on_the_same_phase():
    with TestClient(api.app) as c:
        _seed("p-chance")
        _seed("p-other")
        api.hub.proposal_moment.update({"p-chance": {"phase_id": "ph1", "stoppage_id": None, "priority": 70},
                                        "p-other": {"phase_id": "ph2", "stoppage_id": None, "priority": 40}})
        _seed("p-goal")
        api.hub.proposal_moment["p-goal"] = {"phase_id": "ph1", "stoppage_id": None, "priority": 100}
        c.portal.call(api._supersede, "p-goal", "ph1", None, 100)
        assert api.hub.proposals["p-chance"].status == S.SUPERSEDED
        assert api.hub.proposals["p-other"].status == S.PROPOSED, "different phase: untouched"
        row = [r for r in _rows(c) if r["proposal_id"] == "p-chance"]
        assert [(r["action"], r["actor"]) for r in row] == [("supersede", "supersession")]
        assert c.post("/proposals/p-chance/approve", json={"actor": "op"}).status_code == 409


def test_live_hero_scene_logs_one_row_per_transition():
    with TestClient(api.app) as c:
        c.get("/api/replay", params={"seed": 42, "speed": 1})
        c.post("/api/replay/jump", params={"minute": 41, "second": 12})
        c.post("/api/replay/speed", params={"x": 8})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not any(p.line.startswith("GOAL") for p in api.hub.proposals.values()):
            time.sleep(0.1)
        chance = next(p for p in api.hub.proposals.values() if "Kai Reed saved (xG 0.38)" in p.line)
        goal = next(p for p in api.hub.proposals.values() if p.line.startswith("GOAL Finn Oakes"))
        assert chance.status == S.SUPERSEDED, "the goal on the same phase replaces the pending chance"
        c.post(f"/proposals/{goal.proposal_id}/override", json={"actor": "gallery-op", "override_line": "GOAL! Oakes!"})
        api.replay_session.task.cancel()
        rows = _rows(c)
        by_pid = {}
        for r in rows:
            by_pid.setdefault(r["proposal_id"], []).append(r["action"])
        assert by_pid[chance.proposal_id] == ["supersede"]
        assert by_pid[goal.proposal_id] == ["override"]
        assert rows[-1]["edited_line"] == "GOAL! Oakes!" and rows[-1]["operator"] == "gallery-op"
        assert rows[-1]["match_period"] == "1" and rows[-1]["match_minute"] in ("41", "42")
        decided = [p for p in api.hub.proposals.values() if p.proposal_id in by_pid]
        assert all(len(by_pid[p.proposal_id]) == 1 for p in decided)


def test_csv_header():
    with TestClient(api.app) as c:
        r = c.get("/api/decisions.csv")
        assert r.headers["content-type"].startswith("text/csv")
        assert r.text.splitlines()[0].split(",") == gate.CSV_FIELDS

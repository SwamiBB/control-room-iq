"""The open demo's limits: far above what a person at the console does, and a budget that falls back, never blocks."""

import asyncio
import time

import api.content_safety as content_safety
import api.main as main
import pytest
from agents.workflow import MomentResult, fallback_explanation
from api.guards import DailyBudget, RateWindow
from api.main import app, hub
from api_factories import moment, proposal
from fastapi.testclient import TestClient


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _seed(pid: str) -> str:
    hub.proposals[pid] = proposal(pid)
    return pid


# ---------- the windows and the budget ----------

def test_a_window_allows_its_limit_then_says_how_long_to_wait():
    clock = Clock()
    w = RateWindow(3, 60.0, clock)
    assert [w.take() for _ in range(3)] == [None, None, None]
    clock.t += 15
    assert w.take() == pytest.approx(45.0)
    clock.t += 45
    assert w.take() is None  # the first event has left the window


def test_the_budget_counts_moments_and_starts_again_each_day():
    day = ["2026-10-27"]
    b = DailyBudget(limit=2, today=lambda: day[0])
    assert [b.take(), b.take(), b.take()] == [True, True, False]
    day[0] = "2026-10-28"
    assert b.take() and b.used == 1


# ---------- the routes ----------

def test_decisions_far_above_a_person_s_pace_get_a_429_with_retry_after():
    hub.decision_rate = RateWindow(2)
    c = TestClient(app)
    assert c.post(f"/proposals/{_seed('p-1')}/approve").status_code == 200
    assert c.post(f"/proposals/{_seed('p-2')}/hold").status_code == 200
    r = c.post(f"/proposals/{_seed('p-3')}/reject")
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert hub.proposals["p-3"].status == "proposed"  # nothing was decided


def test_the_defaults_leave_room_for_a_busy_operator():
    c = TestClient(app)
    codes = {c.post(f"/proposals/{_seed(f'p-{i}')}/approve").status_code for i in range(60)}
    assert codes == {200}  # 60 fires in a few seconds: still well under the limit


def test_a_replay_right_after_the_last_one_ended_waits_its_cooldown():
    hub.replay_finished_at = time.monotonic()
    r = TestClient(app).post("/matches/replay", json={"file": "data/reference/match-042.jsonl"})
    assert r.status_code == 429 and "start another" in r.json()["detail"]


def test_once_the_day_s_budget_is_spent_moments_use_the_templates(monkeypatch):
    hub.budget = DailyBudget(limit=0)
    used = []

    async def with_models(_m, **_kwargs):
        used.append("models")
        raise AssertionError("the models must not be called once the budget is spent")

    async def from_templates(m, **_kwargs):
        used.append("templates")
        return MomentResult(moment=m, explanation=fallback_explanation(m), line="l", variants=[], proposal=None,
                            failures=[], notes=[])

    monkeypatch.setattr(main.pipeline, "process", with_models)
    monkeypatch.setattr(main.templates, "process", from_templates)
    m = moment()
    asyncio.run(main._handle_moment(m))
    assert used == ["templates"]
    assert any("model budget" in n for n in hub.results[m.moment_id]["notes"])  # the console says why


# ---------- the override check ----------

def _remote_check(monkeypatch, analyze):
    """The tests run offline, where only the banned-topic rule runs: switch the remote check on, with fakes."""
    from dataclasses import replace

    async def token():
        return "t"

    monkeypatch.setattr(content_safety, "settings", replace(content_safety.settings, offline=False))
    monkeypatch.setenv("AZURE_CONTENT_SAFETY_ENDPOINT", "https://content-safety.example")
    monkeypatch.setattr(content_safety, "_token", token)
    monkeypatch.setattr(content_safety, "_analyze", analyze)


def test_an_override_on_a_banned_topic_is_refused_and_nothing_airs():
    r = TestClient(app).post(f"/proposals/{_seed('p-ban')}/override",
                             json={"override_line": "What a dive, the referee is blind"})
    assert r.status_code == 422 and "kept off air" in r.json()["detail"]  # one sentence the console shows
    assert hub.proposals["p-ban"].status == "proposed" and hub.packets == []


def test_an_override_content_safety_flags_is_refused(monkeypatch):
    async def analyze(_endpoint, _text, _token):
        return {"Hate": 4, "Sexual": 0, "SelfHarm": 0, "Violence": 0}

    _remote_check(monkeypatch, analyze)
    r = TestClient(app).post(f"/proposals/{_seed('p-cs')}/override", json={"override_line": "something hateful"})
    assert r.status_code == 422 and r.json()["detail"].endswith("flagged it (hate)")
    assert hub.packets == []


def test_match_language_passes_the_violence_threshold(monkeypatch):
    async def analyze(_endpoint, _text, _token):
        return {"Hate": 0, "Sexual": 0, "SelfHarm": 0, "Violence": 2}  # Low: "he smashed it in"

    _remote_check(monkeypatch, analyze)
    r = TestClient(app).post(f"/proposals/{_seed('p-ok')}/override", json={"override_line": "He smashed it in!"})
    assert r.status_code == 200 and r.json()["override_line"] == "He smashed it in!"


def test_an_override_that_can_t_be_checked_is_refused(monkeypatch):
    async def analyze(_endpoint, _text, _token):
        raise TimeoutError

    _remote_check(monkeypatch, analyze)
    r = TestClient(app).post(f"/proposals/{_seed('p-503')}/override", json={"override_line": "A fine line"})
    assert r.status_code == 424 and hub.packets == []  # not 503, which the console reads as "API down"


def test_in_azure_an_unconfigured_check_refuses_rather_than_skips(monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(content_safety, "settings", replace(content_safety.settings, offline=False))
    monkeypatch.delenv("AZURE_CONTENT_SAFETY_ENDPOINT", raising=False)
    monkeypatch.setenv("CONTAINER_APP_NAME", "api")
    r = TestClient(app).post(f"/proposals/{_seed('p-cfg')}/override", json={"override_line": "A fine line"})
    assert r.status_code == 424


def test_a_replay_faster_than_the_console_s_fastest_is_refused():
    r = TestClient(app).post("/matches/replay", json={"file": "data/reference/match-042.jsonl", "speed": 1000})
    assert r.status_code == 422 and "50x" in r.json()["detail"]


def test_requests_for_cards_that_don_t_exist_don_t_use_the_limit():
    hub.decision_rate = RateWindow(1)
    c = TestClient(app)
    assert {c.post(f"/proposals/nope-{i}/approve").status_code for i in range(5)} == {404}
    assert c.post(f"/proposals/{_seed('p-real')}/approve").status_code == 200  # the operator is not locked out


def test_after_a_failed_replay_run_again_works_at_once():
    import asyncio as aio

    aio.run(main._finish_replay("ValueError: bad line"))
    assert hub.replay_finished_at is None


def test_an_override_refused_for_too_many_decisions_doesn_t_use_up_the_override_limit():
    hub.decision_rate, hub.override_rate = RateWindow(0), RateWindow(1)
    c = TestClient(app)
    r = c.post(f"/proposals/{_seed('p-o1')}/override", json={"override_line": "A fine line"})
    assert r.status_code == 429 and "decisions" in r.json()["detail"]
    hub.decision_rate = RateWindow(5)  # decisions free up
    assert c.post(f"/proposals/{_seed('p-o2')}/override", json={"override_line": "A fine line"}).status_code == 200

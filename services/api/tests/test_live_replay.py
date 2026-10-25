"""The match keeps playing while agents write (#51), a goal takes over its move's cards (#50), and building the
match folder stays off the event loop (#42)."""

import asyncio
import threading
from types import SimpleNamespace

import api.main as main
from agents.workflow import fallback_explanation
from api.main import _drain_moments, _start_match, _start_moment, hub
from api_factories import match_state, moment, proposal
from crq_schemas import MomentKind, PhaseSummary, ProposalStatus
from simulator.cli import build_meta


def _on_move(phase: str = "ph-1", **overrides):
    state = match_state(current_phase=PhaseSummary(phase_id=phase, team="har", start_play_ms=0))
    return moment(**({"beat": "result", "state": state} | overrides))


class SlowPipeline:
    """Stands in for the agents: takes a while, then proposes a card for the moment."""

    def __init__(self, delay: float = 0.05) -> None:
        self.delay, self.calls = delay, []

    async def process(self, m, **_kwargs):
        self.calls.append(m.moment_id)
        await asyncio.sleep(self.delay)
        return SimpleNamespace(moment=m, explanation=fallback_explanation(m), line="A line", variants=[], failures=[],
                               notes=[], intel=None,
                               proposal=proposal(f"p-{m.moment_id}", moment_id=m.moment_id))


def test_a_moment_is_handed_to_the_agents_without_waiting_for_them(monkeypatch):
    fake = SlowPipeline(delay=0.2)
    monkeypatch.setattr(main, "pipeline", fake)

    async def scenario():
        await _start_moment(_on_move())
        await asyncio.sleep(0.02)  # the agents have started and are still writing; the match goes on meanwhile
        mid_write = (list(fake.calls), dict(hub.proposals))
        await _drain_moments()
        return mid_write

    calls, proposals = asyncio.run(scenario())
    assert calls == ["mo-1"] and proposals == {}
    assert "p-mo-1" in hub.proposals and hub.moment_tasks == set()


def test_a_goal_supersedes_the_pending_card_of_its_move(monkeypatch):
    monkeypatch.setattr(main, "pipeline", SlowPipeline())

    async def scenario():
        await _start_moment(_on_move(moment_id="save"))
        await _drain_moments()  # the save's card is on the desk
        await _start_moment(_on_move(moment_id="goal", kind=MomentKind.GOAL, importance=1.0))
        await _drain_moments()

    asyncio.run(scenario())
    save = hub.proposals["p-save"]
    assert save.status == ProposalStatus.EXPIRED and save.decided_by == "supersession"
    assert hub.decisions[-1].proposal_id == "p-save" and "superseded by the goal" in hub.decisions[-1].reasoning
    assert any(pid.startswith("p-goal") for pid in hub.proposals)


def test_a_card_finished_after_its_goal_never_reaches_the_desk(monkeypatch):
    # The save's agents are slower than the goal arriving: the card would otherwise appear after the goal.
    monkeypatch.setattr(main, "pipeline", SlowPipeline(delay=0.1))
    sent = []

    async def capture(msg):
        sent.append(msg)

    monkeypatch.setattr(hub, "broadcast_operators", capture)

    async def scenario():
        await _start_moment(_on_move(moment_id="save"))
        await _start_moment(_on_move(moment_id="goal", kind=MomentKind.GOAL, importance=1.0))
        await _drain_moments()

    asyncio.run(scenario())
    assert "p-save" not in hub.proposals
    save_moment = next(m for m in sent if m["type"] == "moment" and m["moment"]["moment_id"] == "save")
    assert save_moment["notes"] == ["No graphic proposed: the goal on the same move took over"]


def test_a_goal_leaves_other_moves_alone(monkeypatch):
    monkeypatch.setattr(main, "pipeline", SlowPipeline())

    async def scenario():
        await _start_moment(_on_move("ph-1", moment_id="chance"))
        await _drain_moments()
        await _start_moment(_on_move("ph-2", moment_id="goal", kind=MomentKind.GOAL, importance=1.0))
        await _drain_moments()

    asyncio.run(scenario())
    assert hub.proposals["p-chance"].status == ProposalStatus.PROPOSED


def test_a_new_match_stops_the_old_matchs_agents(monkeypatch):
    fake = SlowPipeline(delay=5)
    monkeypatch.setattr(main, "pipeline", fake)

    async def scenario():
        await _start_moment(_on_move())
        await asyncio.sleep(0.02)  # the old match's agents are mid-write
        task = next(iter(hub.moment_tasks))
        hub.new_match(build_meta(7))
        await asyncio.sleep(0)  # let the cancellation land
        return task

    task = asyncio.run(scenario())
    assert fake.calls == ["mo-1"] and task.cancelled() and hub.proposals == {}


def test_a_goal_that_arrives_during_the_broadcast_still_takes_the_card(monkeypatch):
    # The save's moment is being broadcast when the goal lands: the card must still not be queued.
    monkeypatch.setattr(main, "pipeline", SlowPipeline())

    async def goal_lands_mid_broadcast(msg):
        if msg["type"] == "moment" and msg["moment"]["moment_id"] == "save":
            hub.goal_phases.add("ph-1")

    monkeypatch.setattr(hub, "broadcast_operators", goal_lands_mid_broadcast)

    async def scenario():
        await _start_moment(_on_move(moment_id="save"))
        await _drain_moments()

    asyncio.run(scenario())
    assert "p-save" not in hub.proposals
    assert hub.results["save"]["notes"] == [main.GOAL_TOOK_OVER]  # the reason is kept, not lost


def test_a_goal_without_a_move_supersedes_nothing(monkeypatch):
    monkeypatch.setattr(main, "pipeline", SlowPipeline())

    async def scenario():
        await _start_moment(_on_move(moment_id="chance"))
        await _drain_moments()
        await _start_moment(moment("goal", beat="result", kind=MomentKind.GOAL, importance=1.0))  # no phase
        await _drain_moments()

    asyncio.run(scenario())
    assert hub.proposals["p-chance"].status == ProposalStatus.PROPOSED
    assert any(pid.startswith("p-goal") for pid in hub.proposals) and hub.goal_phases == set()


def test_a_held_card_is_not_superseded(monkeypatch):
    # Holding is the operator's (or the timer's) decision; supersession only takes cards nobody has decided on.
    monkeypatch.setattr(main, "pipeline", SlowPipeline())

    async def scenario():
        await _start_moment(_on_move(moment_id="save"))
        await _drain_moments()
        hub.proposals["p-save"].status = ProposalStatus.HELD
        await _start_moment(_on_move(moment_id="goal", kind=MomentKind.GOAL, importance=1.0))
        await _drain_moments()

    asyncio.run(scenario())
    assert hub.proposals["p-save"].status == ProposalStatus.HELD


def test_a_failed_replay_stops_its_agents(monkeypatch):
    fake = SlowPipeline(delay=5)
    monkeypatch.setattr(main, "pipeline", fake)
    seen = {}

    async def drive_then_fail(req):
        await _start_moment(_on_move())
        await asyncio.sleep(0.02)  # the agents are writing when the replay breaks
        seen["task"] = next(iter(hub.moment_tasks))
        raise RuntimeError("feed broke")

    monkeypatch.setattr(main, "_drive_replay", drive_then_fail)

    async def scenario():
        await main._replay(main.ReplayRequest())
        await asyncio.sleep(0)  # checked inside the loop: asyncio.run would cancel leftovers on its own at exit
        return seen["task"].cancelled(), set(hub.moment_tasks)

    cancelled, left = asyncio.run(scenario())
    assert fake.calls == ["mo-1"] and cancelled and left == set() and hub.proposals == {}


def test_the_supersession_log_names_the_match_minute():
    first, second = moment(period=1, t_ms=41 * 60_000 + 15_000), moment(period=2, t_ms=18 * 60_000 + 5_000)
    assert (main._clock(first), main._clock(second)) == ("41:15", "63:05")


def test_the_match_folder_is_built_off_the_event_loop(monkeypatch):
    seen = {}

    class RecordingFolder:
        def __init__(self, meta):
            seen["thread"] = threading.current_thread()
            self.state = None

    monkeypatch.setattr(main, "StateFolder", RecordingFolder)
    asyncio.run(_start_match(build_meta(7)))
    assert seen["thread"] is not threading.main_thread()


def test_the_match_slows_to_real_time_while_agents_write(monkeypatch):
    # At 20x, the ~15 s the agents take would be minutes of match: the card must not arrive long after its moment.
    monkeypatch.setattr(main, "pipeline", SlowPipeline(delay=0.2))
    req = main.ReplayRequest(speed=20.0)

    async def scenario():
        before = main._effective_speed(req)
        await _start_moment(_on_move())
        writing = main._effective_speed(req)
        await _drain_moments()
        hub.proposals["p-mo-1"].status = ProposalStatus.HELD  # decided: the match may run fast again
        return before, writing, main._effective_speed(req)

    assert asyncio.run(scenario()) == (20.0, 1.0, 20.0)


def test_a_fourth_moment_waits_for_a_free_slot(monkeypatch):
    fake = SlowPipeline(delay=0.2)
    monkeypatch.setattr(main, "pipeline", fake)

    async def scenario():
        for i in range(main.MAX_PARALLEL_MOMENTS + 1):
            await _start_moment(_on_move(f"ph-{i}", moment_id=f"mo-{i}"))
        await asyncio.sleep(0.05)
        started = list(fake.calls)
        await _drain_moments()
        return started

    started = asyncio.run(scenario())
    assert len(started) == main.MAX_PARALLEL_MOMENTS and len(fake.calls) == main.MAX_PARALLEL_MOMENTS + 1


def test_a_moment_that_crashes_is_logged_and_the_others_carry_on(monkeypatch, caplog):
    class Breaks(SlowPipeline):
        async def process(self, m, **kwargs):
            if m.moment_id == "bad":
                raise RuntimeError("agents broke")
            return await super().process(m, **kwargs)

    monkeypatch.setattr(main, "pipeline", Breaks())

    async def scenario():
        await _start_moment(_on_move("ph-1", moment_id="bad"))
        await _start_moment(_on_move("ph-2", moment_id="good"))
        await _drain_moments()

    asyncio.run(scenario())
    assert "moment bad failed" in caplog.text and "agents broke" in caplog.text
    assert "p-good" in hub.proposals and hub.moment_tasks == set()

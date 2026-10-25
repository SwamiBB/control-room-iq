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
    monkeypatch.setattr(main, "pipeline", SlowPipeline(delay=0.2))

    async def scenario():
        await _start_moment(_on_move())
        started = dict(hub.proposals)  # right after the hand-off: the agents are still writing
        await _drain_moments()
        return started

    started = asyncio.run(scenario())
    assert started == {} and "p-mo-1" in hub.proposals and hub.moment_tasks == set()


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
    monkeypatch.setattr(main, "pipeline", SlowPipeline(delay=5))

    async def scenario():
        await _start_moment(_on_move())
        task = next(iter(hub.moment_tasks))
        hub.new_match(build_meta(7))
        await asyncio.sleep(0)  # let the cancellation land
        return task

    task = asyncio.run(scenario())
    assert task.cancelled() and hub.proposals == {}


def test_the_match_folder_is_built_off_the_event_loop(monkeypatch):
    seen = {}

    class RecordingFolder:
        def __init__(self, meta):
            seen["thread"] = threading.current_thread()
            self.state = None

    monkeypatch.setattr(main, "StateFolder", RecordingFolder)
    asyncio.run(_start_match(build_meta(7)))
    assert seen["thread"] is not threading.main_thread()

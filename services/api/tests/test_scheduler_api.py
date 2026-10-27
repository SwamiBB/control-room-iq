"""The scheduler in the API: a slot on arrival, placement when fired, queued graphics sent when their slot starts."""

import asyncio

import api.main as main
from api.main import ViewerPrefs, app, hub
from api_factories import RecordingSocket, match_state, moment, proposal
from crq_schemas import MomentKind, OverlayLayer, Persona
from fastapi.testclient import TestClient


async def _queue(pid, m=None, **kw):
    m = m or moment(moment_id=f"mo-{pid}")
    hub.moments[m.moment_id] = m
    await main._queue_proposal(proposal(pid, moment_id=m.moment_id, t_start_ms=0, t_end_ms=10_000, **kw))
    return pid


def _desk(pid, m=None, **kw):
    return asyncio.run(_queue(pid, m, **kw))


def test_a_card_on_the_desk_already_has_its_slot_and_hold_advice():
    hub.clock.play_ms = 600_000
    pid = _desk("p-1", moment(state=match_state(pressure_trend="rising")))
    p = hub.proposals[pid]
    assert (p.t_in_ms, p.t_out_ms) == (600_000, 610_000)  # the running order shows a real block, not "unscheduled"
    assert p.hold_advice.recommend_hold


def test_a_goal_takes_down_the_lower_third_on_air():
    hub.clock.play_ms = 600_000
    c = TestClient(app)
    c.post(f"/proposals/{_desk('p-lt')}/approve")
    goal = moment(moment_id="mo-goal", kind=MomentKind.GOAL)
    c.post(f"/proposals/{_desk('p-goal', goal, layer=OverlayLayer.FULL_SCREEN, priority=1)}/approve")
    lead = hub.packets[-1]
    assert lead.t_in_ms == 600_000 and "c-p-lt" in lead.replaces


def test_a_graphic_for_a_busy_layer_is_sent_when_its_slot_starts():
    viewer = RecordingSocket()
    hub.viewers[viewer] = ViewerPrefs(persona=Persona.FAN)
    hub.clock.play_ms, hub.replay_speed = 600_000, 1000.0  # a replay is running (fast, so the wait is short)

    async def scenario():
        await main._decide(await _queue("p-first"), main.ProposalStatus.APPROVED, main.Decision())
        # The same story, so only the busy layer makes it wait.
        await main._decide(await _queue("p-next", hub.moments["mo-p-first"]), main.ProposalStatus.APPROVED,
                           main.Decision())
        queued = hub.proposals["p-next"]
        before = (len(viewer.of_type("overlay")), queued.status)
        hub.clock.play_ms = 610_000  # the match reaches the end of the first graphic
        await asyncio.gather(*hub.air_tasks)
        return before, (len(viewer.of_type("overlay")), queued.status)

    before, after = asyncio.run(scenario())
    assert before == (1, "approved") and after == (2, "aired")  # aired only when actually sent
    assert hub.packets[-1].t_in_ms == 610_000


def test_the_slot_is_taken_from_the_live_play_time_not_the_next_event():
    # The replay has moved the clock to the next event 8 s ahead and is still waiting out that gap.
    hub.clock.play_ms, hub.pace_left_ms, hub.replay_speed = 618_000, 8_000.0, 1.0
    pid = _desk("p-live")
    assert hub.proposals[pid].t_in_ms == 610_000


def test_a_queued_graphic_cut_before_its_slot_never_airs_and_is_not_counted():
    viewer = RecordingSocket()
    hub.viewers[viewer] = ViewerPrefs(persona=Persona.FAN)
    hub.clock.play_ms, hub.replay_speed = 600_000, 1000.0

    async def scenario():
        await main._decide(await _queue("p-on"), main.ProposalStatus.APPROVED, main.Decision())
        await main._decide(await _queue("p-wait", hub.moments["mo-p-on"]), main.ProposalStatus.APPROVED,
                           main.Decision())
        goal = moment(moment_id="mo-goal", kind=MomentKind.GOAL)
        await main._decide(await _queue("p-goal", goal, layer=OverlayLayer.FULL_SCREEN, priority=1),
                           main.ProposalStatus.APPROVED, main.Decision())
        hub.clock.play_ms = 611_000
        await asyncio.gather(*hub.air_tasks)

    asyncio.run(scenario())
    assert "c-p-wait" not in [pk.cue_id for pk in hub.packets]  # off the schedule, so not counted as aired
    assert hub.proposals["p-wait"].status == "approved"
    assert len(viewer.of_type("overlay")) == 2  # the first graphic and the goal


def test_with_the_clock_stopped_a_new_graphic_cuts_the_one_on_its_layer():
    viewer = RecordingSocket()
    hub.viewers[viewer] = ViewerPrefs(persona=Persona.FAN)
    hub.clock.play_ms, hub.replay_speed = 600_000, None
    c = TestClient(app)
    c.post(f"/proposals/{_desk('p-a')}/approve")
    c.post(f"/proposals/{_desk('p-b', moment(moment_id='mo-p-a'))}/approve")
    assert len(viewer.of_type("overlay")) == 2  # no clock to wait for: nothing is left unsent
    assert hub.packets[-1].replaces == ["c-p-a"]  # and nothing stacks on the layer

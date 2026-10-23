import os

os.environ["CRQ_OFFLINE"] = "1"

import asyncio  # noqa: E402
from itertools import combinations  # noqa: E402

import pytest  # noqa: E402
from api.offline import replay_offline  # noqa: E402
from api.scheduler import LayerScheduler, clashes, match_ms  # noqa: E402
from crq_schemas import MomentKind, OverlayLayer, OverlayProposal  # noqa: E402
from simulator.cli import write_match  # noqa: E402
from simulator.scripted import DATA_DIR, generate  # noqa: E402

L3, FS, TICK = OverlayLayer.LOWER_THIRD, OverlayLayer.FULL_SCREEN, OverlayLayer.TICKER


def _p(pid, layer, start, dur=10_000):
    return OverlayProposal(proposal_id=pid, match_id="m", moment_id="mo-" + pid, layer=layer, t_start_ms=start,
                           t_end_ms=start + dur, line=pid, reasoning="r", priority=0.5)


def test_earliest_free_gap_and_one_story_per_window():
    s = LayerScheduler("m")
    a = s.schedule(_p("a", L3, 5_000), now_ms=5_000)
    b = s.schedule(_p("b", L3, 8_000), now_ms=8_000)  # same layer and same window: next window
    t = s.schedule(_p("t", TICK, 8_000), now_ms=8_000)  # ticker is exempt from the window rule
    assert (a.t_start_ms, a.t_end_ms) == (5_000, 15_000)
    assert b.t_start_ms == 60_000 and b.window_id == "m-w0001"
    assert t.t_start_ms == 8_000


def test_full_screen_clashes_with_lower_third_but_not_ticker():
    assert clashes(FS, L3) and clashes(L3, FS) and not clashes(FS, TICK)


def test_goal_preempts_the_running_lower_third():
    s = LayerScheduler("m")
    s.schedule(_p("chance", L3, 2_474_300), now_ms=2_474_300)
    s.approve("chance", now_ms=2_474_300)
    goal = s.schedule(_p("goal", FS, 2_476_400, 18_000), now_ms=2_476_400, preempts=True)
    s.approve("goal", now_ms=2_476_400)
    assert goal.t_start_ms == 2_476_400
    assert s.bookings["chance"].end == 2_476_400, "the lower third is cut when the goal goes full screen"
    assert [i.proposal_id for i in s.screen(2_480_000).on_air] == ["goal"]


def test_hold_frees_the_slot_and_approval_from_hold_rebooks():
    s = LayerScheduler("m")
    s.schedule(_p("a", L3, 0), now_ms=0)
    s.hold("a")
    b = s.schedule(_p("b", L3, 1_000), now_ms=1_000)
    assert b.t_start_ms == 1_000 and [i.proposal_id for i in s.screen(1_000).held] == ["a"]
    again = s.approve("a", now_ms=20_000)
    assert again.start >= 60_000, "back from hold it takes the next free window"


def test_halves_never_collide():
    assert match_ms(2, 0) > match_ms(1, 50 * 60_000)


@pytest.mark.parametrize("story", sorted(DATA_DIR.glob("storyline*.json")), ids=lambda p: p.stem)
def test_full_replay_never_double_books_a_layer(story, tmp_path):
    meta, events = generate(story)
    path = tmp_path / "match.jsonl"
    write_match(path, meta, events)
    rows = asyncio.run(replay_offline(path))
    s = LayerScheduler(meta.match_id)
    for r in rows:
        if not r.proposal:
            continue
        m = r.moment
        p = r.proposal.model_copy(update={"t_start_ms": match_ms(m.period, r.proposal.t_start_ms),
                                          "t_end_ms": match_ms(m.period, r.proposal.t_end_ms)})
        now = match_ms(m.period, m.t_ms)
        s.schedule(p, now, preempts=m.kind in (MomentKind.GOAL, MomentKind.RED_CARD))
        s.approve(p.proposal_id, now)  # the operator approves everything: the worst case for collisions
    booked = [b for b in s.bookings.values() if b.end > b.start]
    assert len(booked) >= 10
    for a, b in combinations(booked, 2):
        if clashes(a.layer, b.layer):
            assert a.end <= b.start or b.end <= a.start, (a, b)

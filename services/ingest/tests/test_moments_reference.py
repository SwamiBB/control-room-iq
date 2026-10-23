"""Moment detector over the reference matches: the demo moments, their beats, priorities and snapshots."""

import json

import pytest
from crq_schemas import MomentKind
from ingest.stats import StateFolder
from simulator.scripted import DATA_DIR, generate


def _fold(story: str):
    meta, events = generate(DATA_DIR / story)
    folder = StateFolder(meta)
    return folder, [m for ev in events for m in folder.apply(ev)]


@pytest.fixture(scope="module")
def ref():
    return _fold("storyline.json")


def _at(moments, kind, minute, period=1):
    return [m for m in moments if m.kind == kind and m.period == period and m.state.minute == minute]


def test_big_chance_has_strike_then_result(ref):
    _, moments = ref
    result = _at(moments, MomentKind.BIG_CHANCE, 23)[0]
    strike = next(m for m in reversed(moments[:moments.index(result)]) if m.kind == MomentKind.SHOT)
    assert (strike.beat, strike.priority, strike.player) == ("strike", 0, "har-07")
    assert strike.importance < 0.3, "strike beats go to the cue, never to the agents"
    assert (result.beat, result.priority, result.snapshot["xg"]) == ("result", 70, 0.29)
    assert result.snapshot["chance_quality"] == "about 1 in 3 chances like this go in"
    assert result.phase_id == strike.phase_id


def test_stoppage_then_card_on_the_same_stoppage(ref):
    _, moments = ref
    stop = _at(moments, MomentKind.STOPPAGE, 31)[0]
    card = next(m for m in moments if m.kind == MomentKind.CARD and m.stoppage_id == stop.stoppage_id)
    assert stop.snapshot["reason"] == "foul" and stop.snapshot["offender"]["player_id"] == "nfu-04"
    assert stop.snapshot["fouled"]["name"] == "Kai Reed"
    assert stop.snapshot["restart"]["type"] == "free_kick" and stop.snapshot["restart"]["team"] == "har"
    assert card.priority > stop.priority, "the card supersedes the plain stoppage"
    assert card.snapshot["color"] == "yellow"


def test_hero_scene_hold_then_goal_supersedes(ref):
    _, moments = ref
    chance = next(m for m in _at(moments, MomentKind.BIG_CHANCE, 41) if m.snapshot["xg"] == 0.38)
    goal = _at(moments, MomentKind.GOAL, 41)[0]
    assert chance.snapshot["hold_advice"]["recommend"] == "hold"
    assert goal.phase_id == chance.phase_id and goal.priority > chance.priority
    assert goal.snapshot["how"].startswith("rebound after Kai Reed")
    assert goal.snapshot["goal"]["attrs"]["preempts"] == ["lower_third"]
    assert goal.snapshot["score"] == {"har": 1, "nfu": 0}


def test_late_chance_says_air(ref):
    _, moments = ref
    late = _at(moments, MomentKind.BIG_CHANCE, 78, period=2)[0]
    assert late.snapshot["shooter"]["player_id"] == "nfu-09"
    assert late.snapshot["hold_advice"]["recommend"] == "air"


def test_every_snapshot_cites_its_trigger(ref):
    _, moments = ref
    for m in moments:
        if m.snapshot:
            assert m.trigger_event_id in json.dumps(m.snapshot), m.kind


def test_derived_state_at_full_time(ref):
    folder, _ = ref
    s = folder.state
    assert [e.chance_rank for e in s.shot_ledger] == list(range(1, len(s.shot_ledger) + 1))
    assert set(s.windows) == set(s.pressure_trend) == {"har", "nfu"}
    assert s.momentum_label in ("home_on_top", "away_on_top", "even", "swinging")
    assert any(m.kind == "first_goal" and m.subject == "har" for m in s.milestones)
    assert {r.kind for r in s.recap_points} >= {"goal", "big_chance", "card"}


def test_match_two_red_card_offside_and_penalty():
    _, moments = _fold("storyline_m2.json")
    red = next(m for m in moments if m.kind == MomentKind.RED_CARD)
    assert (red.player, red.priority, red.snapshot["sent_off"]) == ("irb-04", 90, True)
    assert any(m.kind == MomentKind.STOPPAGE and m.snapshot["reason"] == "offside" for m in moments)
    pen = next(m for m in moments if m.kind == MomentKind.GOAL and m.player == "rva-10")
    assert pen.snapshot["how"] == "penalty"


def test_match_three_second_yellow_is_a_red_card_moment():
    _, moments = _fold("storyline_m3.json")
    red = next(m for m in moments if m.kind == MomentKind.RED_CARD)
    assert red.player == "har-05" and red.snapshot["color"] == "second_yellow"
    assert red.snapshot["card_history"] == {"yellow": 1, "red": 1}
    assert [m.snapshot["score"] for m in moments if m.kind == MomentKind.GOAL][-1] == {"nfu": 2, "har": 2}

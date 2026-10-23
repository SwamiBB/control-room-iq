"""State engine over the reference matches (v0.2): beats, derived state and the demo moments."""

import pytest
from crq_schemas import MomentKind
from ingest.derive import chance_quality, zone
from ingest.stats import StateFolder
from simulator.scripted import DATA_DIR, generate, opta_clock


def _fold(story: str):
    meta, events = generate(DATA_DIR / story)
    folder = StateFolder(meta)
    return folder, [m for ev in events for m in folder.apply(ev)]


@pytest.fixture(scope="module")
def ref():
    return _fold("storyline.json")


def _at(moments, kind, minute, period=1, beat=None):
    return [m for m in moments if m.kind == kind and m.period == period and opta_clock(m.period, m.t_ms)[0] == minute
            and (beat is None or m.beat == beat)]


def test_big_chance_is_two_beats_on_the_same_phase(ref):
    _, moments = ref
    chance = _at(moments, MomentKind.BIG_CHANCE, 23, beat="chance")[0]
    result = _at(moments, MomentKind.BIG_CHANCE, 23, beat="result")[0]
    assert chance.player == result.player == "har-07"
    assert chance.play_ms <= result.play_ms and result.play_ms - chance.play_ms < 1000
    assert chance.state.current_phase.phase_id == result.state.current_phase.phase_id


def test_stoppage_then_card_for_the_31st_minute_foul(ref):
    _, moments = ref
    stop = _at(moments, MomentKind.STOPPAGE, 31)[0]
    card = _at(moments, MomentKind.CARD, 32)[0]
    assert stop.summary == "Foul by Zed North; free kick" and stop.importance >= 0.35, "free kick at the box: propose"
    assert stop.state.last_stoppage.reason == "foul" and stop.state.last_stoppage.against_team == "nfu"
    assert card.player == "nfu-04" and card.summary == "Yellow card Zed North"


def test_hero_scene_reads_as_rising_pressure_and_the_late_chance_does_not(ref):
    _, moments = ref
    hero = next(m for m in _at(moments, MomentKind.BIG_CHANCE, 41, beat="result") if "0.38" in m.summary)
    goal = _at(moments, MomentKind.GOAL, 41)[0]
    late = _at(moments, MomentKind.BIG_CHANCE, 78, period=2, beat="result")[0]
    assert hero.state.pressure_trend == "rising", "the scheduler's hold advice reads this"
    assert hero.state.home.shots_last_5min >= 4 and hero.state.home.xg_last_5min >= 0.6
    assert goal.beat == "result" and goal.state.home.goals == 1
    assert late.state.pressure_trend != "rising", "one isolated chance is not pressure building"


def test_ordinary_fouls_reach_the_fan_but_not_the_operator(ref):
    _, moments = ref
    stops = [m for m in moments if m.kind == MomentKind.STOPPAGE]
    assert stops and all(m.importance >= 0.3 for m in stops)
    assert any(m.importance < 0.35 for m in stops)


def test_derived_state_at_full_time(ref):
    folder, moments = ref
    s = folder.state
    assert [r.chance_rank for r in sorted(s.shots, key=lambda r: r.chance_rank)] == list(range(1, len(s.shots) + 1))
    assert s.shots[0].zone and all(r.play_ms > 0 for r in s.shots)
    assert s.momentum_label in ("home_pushing", "balanced", "away_pushing")
    assert s.last_stoppage.reason == "match_end"
    assert s.recap_points and all(p.importance >= 0.6 for p in s.recap_points)
    assert {p.kind for p in s.recap_points} >= {"goal", "big_chance", "half_end"}
    assert all(m.play_ms > 0 for m in moments[1:])
    assert folder.crowd_level > 0


def test_match_two_red_card_offside_and_penalty():
    _, moments = _fold("storyline_m2.json")
    red = next(m for m in moments if m.kind == MomentKind.CARD and m.player == "irb-04" and m.importance > 0.45)
    assert red.summary == "Red card Quin Frost" and red.importance == 0.7
    assert any(m.kind == MomentKind.STOPPAGE and m.summary.startswith("Offside against Yan Thorne") for m in moments)
    pen = next(m for m in moments if m.kind == MomentKind.STOPPAGE and m.summary.endswith("penalty"))
    assert pen.importance == 0.4


def test_match_three_comeback_and_second_yellow():
    folder, moments = _fold("storyline_m3.json")
    assert any(m.kind == MomentKind.CARD and m.summary == "Second yellow, sent off Wes Oak" for m in moments)
    assert (folder.state.home.goals, folder.state.away.goals) == (2, 2)


def test_rules():
    assert zone(89, 47) == "inside the box, centre" and zone(79, 70) == "edge of the box, left"
    assert chance_quality(0.38) == "about 1 in 3 chances like this go in"
    assert chance_quality(0.76) == "about 8 in 10 chances like this go in"

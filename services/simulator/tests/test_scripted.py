"""The reference matches: deterministic, scripted moments at their minutes, the new event types wired."""

import statistics

import pytest
from crq_schemas import EventType
from simulator.calibrate import calibrate_engine
from simulator.scripted import DATA_DIR, expand_beats, generate, load_storyline, opta_clock
from simulator.tracking import build_tracking

STORIES = sorted(DATA_DIR.glob("storyline*.json"))
REF = DATA_DIR / "storyline.json"


@pytest.fixture(scope="module")
def ref():
    return generate(REF)


@pytest.fixture(scope="module", params=STORIES, ids=lambda p: p.stem)
def match(request):
    return load_storyline(request.param), *generate(request.param)


def test_same_seed_same_file():
    _, a = generate(REF)
    _, b = generate(REF)
    assert [e.model_dump_json() for e in a] == [e.model_dump_json() for e in b]


def test_final_score_is_scripted(match):
    story, _, evs = match
    expected = {k: v for k, v in story["final_score_expected"].items() if k != "note"}
    assert next(e for e in evs if e.type == EventType.MATCH_END).attrs["score"] == expected
    goals = sum(e.type == EventType.SHOT and e.outcome == "goal" for e in evs)
    assert goals == sum(expected.values())
    assert sum(e.type == EventType.KICKOFF and e.attrs.get("after") == "goal" for e in evs) == goals


def test_scripted_moments_land_on_their_minute(match):
    story, _, evs = match
    at = {(e.type, e.player, e.period, e.minute, e.second) for e in evs}
    for b in expand_beats(story["beats"]):
        key = (b["period"], b["minute"], b.get("second", 0))
        if b["kind"] in ("shot", "goal"):
            assert (EventType.SHOT_TAKEN, b["player"], *key) in at, b
        elif b["kind"] == "chance_then_rebound_goal":
            assert (EventType.SHOT_TAKEN, b["chance"]["player"], *key) in at, b
        elif b["kind"] in ("foul", "red_card"):
            assert (EventType.FOUL, b["player"], *key) in at, b
        elif b["kind"] == "penalty_goal":
            assert (EventType.FOUL, b["foul"]["player"], *key) in at, b
        elif b["kind"] == "offside":
            assert (EventType.PASS, b["passer"], *key) in at, b


def test_events_ordered_and_clocked(match):
    _, _, evs = match
    assert [e.seq for e in evs] == list(range(1, len(evs) + 1))
    assert [(e.period, e.t_ms) for e in evs] == sorted((e.period, e.t_ms) for e in evs)
    for e in evs:
        assert (e.minute, e.second) == opta_clock(e.period, e.t_ms)
        assert e.frame is not None


def test_every_shot_follows_its_strike_on_the_same_phase(match):
    _, _, evs = match
    for i, e in enumerate(evs):
        if e.type == EventType.SHOT:
            strike = next(s for s in reversed(evs[:i]) if s.type == EventType.SHOT_TAKEN)
            assert strike.player == e.player and strike.t_ms <= e.t_ms
            assert e.phase_id and strike.phase_id == e.phase_id


def test_hero_scene(ref):
    _, evs = ref
    shots = [e for e in evs if e.type == EventType.SHOT and e.period == 1 and e.minute == 41]
    saved, goal = shots[0], shots[1]
    assert saved.outcome == "saved" and saved.attrs["xg"] == 0.38
    assert goal.outcome == "goal" and goal.phase_id == saved.phase_id
    assert 1500 <= goal.t_ms - saved.t_ms <= 2500
    assert goal.attrs["preempts"] == ["lower_third"]


def test_stoppage_links_foul_card_and_restart(ref):
    _, evs = ref
    foul = next(e for e in evs if e.type == EventType.FOUL and e.player == "nfu-04" and e.minute == 31)
    linked = [e for e in evs if e.stoppage_id == foul.stoppage_id]
    assert {e.type for e in linked} == {EventType.FOUL, EventType.WHISTLE, EventType.STOPPAGE, EventType.CARD}
    stoppage = next(e for e in linked if e.type == EventType.STOPPAGE)
    assert stoppage.attrs == {"reason": "foul", "against": "nfu", "restart": "free_kick"}
    assert next(e for e in linked if e.type == EventType.CARD).attrs["color"] == "yellow"


@pytest.mark.parametrize("story,player", [("storyline_m2.json", "irb-04"), ("storyline_m3.json", "har-05")])
def test_sent_off_player_takes_no_further_part(story, player):
    _, evs = generate(DATA_DIR / story)
    card = next(e for e in evs if e.type == EventType.CARD and e.player == player
                and e.attrs["color"] in ("red", "second_yellow"))
    assert card.attrs["preempts"] == ["lower_third"]
    assert not [e for e in evs if e.player == player and (e.period, e.t_ms) > (card.period, card.t_ms)]


def test_crowd_is_steady_two_hertz(ref):
    _, evs = ref
    for period in (1, 2):
        ts = [e.t_ms for e in evs if e.type == EventType.CROWD and e.period == period]
        assert ts[0] == 0 and {b - a for a, b in zip(ts, ts[1:])} == {500}
    assert all(0 <= e.attrs["level"] <= 1 for e in evs if e.type == EventType.CROWD)


def test_tracking_frames_and_running(ref):
    meta, evs = ref
    frames, summary = build_tracking(meta, evs)
    assert frames[0].frame == 0 and len(frames[0].players) == 22
    assert all(0 <= v <= 100 for f in frames for v in f.ball)
    assert all(b.frame == a.frame + 1 for a, b in zip(frames, frames[1:]) if a.period == b.period)
    outfield = [v for pid, v in summary.items() if not pid.endswith(("-01", "-15"))]
    assert max(v["top_speed_kmh"] for v in outfield) <= 34.5  # capped by pace: (7 + 2.5) m/s
    assert 9.5 <= statistics.median(v["distance_km"] for v in outfield) <= 12.5  # docs/CALIBRATION.md range


def test_calibration_runs():
    rows = calibrate_engine(1000, 3)
    assert {r["key"] for r in rows} >= {"goals", "shots", "passes", "pass_accuracy"}

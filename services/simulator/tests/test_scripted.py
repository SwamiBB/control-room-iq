"""The reference matches: deterministic, scripted moments at their minutes, v0.2 events and attrs."""

import statistics

import pytest
from crq_schemas import EventType
from simulator.calibrate import calibrate_engine
from simulator.scripted import DATA_DIR, expand_beats, generate, load_storyline, opta_clock
from simulator.tracking import build_tracking

STORIES = sorted(DATA_DIR.glob("storyline*.json"))
REF = DATA_DIR / "storyline.json"


def _clock(e):
    return opta_clock(e.period, e.t_ms)


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
    assert sum(e.type == EventType.STOPPAGE and e.attrs["reason"] == "goal" for e in evs) == goals


def test_scripted_moments_land_on_their_minute(match):
    story, _, evs = match
    at = {(e.type, e.player, e.period, *_clock(e)) for e in evs}
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


def test_events_ordered_with_monotonic_play_time(match):
    _, _, evs = match
    assert [e.seq for e in evs] == list(range(1, len(evs) + 1))
    assert [(e.period, e.t_ms) for e in evs] == sorted((e.period, e.t_ms) for e in evs)
    assert [e.play_ms for e in evs] == sorted(e.play_ms for e in evs)
    half_end = next(e for e in evs if e.type == EventType.HALF_END)
    second = next(e for e in evs if e.period == 2)
    assert second.play_ms == half_end.t_ms + second.t_ms, "the second half continues from the end of the first"


def test_only_contract_event_types(match):
    _, _, evs = match
    assert {e.type for e in evs} <= set(EventType)


def test_every_shot_follows_its_strike_on_the_same_phase(match):
    _, _, evs = match
    for i, e in enumerate(evs):
        if e.type == EventType.SHOT:
            strike = next(s for s in reversed(evs[:i]) if s.type == EventType.SHOT_TAKEN)
            assert strike.player == e.player and strike.t_ms <= e.t_ms
            assert e.phase_id and strike.phase_id == e.phase_id
            assert strike.attrs["xg"] == e.attrs["xg"], "the chance beat already knows the chance quality"


def test_hero_scene(ref):
    _, evs = ref
    shots = [e for e in evs if e.type == EventType.SHOT and e.period == 1 and _clock(e)[0] == 41]
    saved, goal = shots[0], shots[1]
    assert saved.outcome == "saved" and saved.attrs["xg"] == 0.38
    assert goal.outcome == "goal" and goal.phase_id == saved.phase_id
    assert 1500 <= goal.t_ms - saved.t_ms <= 2500


def test_stoppage_links_foul_card_and_restart(ref):
    _, evs = ref
    foul = next(e for e in evs if e.type == EventType.FOUL and e.player == "nfu-04" and _clock(e)[0] == 31)
    linked = [e for e in evs if e.stoppage_id == foul.stoppage_id]
    assert {e.type for e in linked} == {EventType.FOUL, EventType.WHISTLE, EventType.STOPPAGE, EventType.CARD}
    stoppage = next(e for e in linked if e.type == EventType.STOPPAGE)
    assert {k: stoppage.attrs[k] for k in ("reason", "against_team", "against_player", "restart")} == {
        "reason": "foul", "against_team": "nfu", "against_player": "nfu-04", "restart": "free_kick"}
    assert stoppage.attrs["restart_x"] is not None
    assert next(e for e in linked if e.type == EventType.CARD).attrs["card"] == "yellow"
    assert all(e.attrs["stoppage_id"] == foul.stoppage_id for e in linked if e.type == EventType.WHISTLE)


def test_half_and_full_time_are_whistled_stoppages(ref):
    _, evs = ref
    reasons = [e.attrs["reason"] for e in evs if e.type == EventType.STOPPAGE]
    assert reasons.count("half_end") == 1 and reasons.count("match_end") == 1
    assert "ball_out" in reasons


@pytest.mark.parametrize("story,player", [("storyline_m2.json", "irb-04"), ("storyline_m3.json", "har-05")])
def test_sent_off_player_takes_no_further_part(story, player):
    _, evs = generate(DATA_DIR / story)
    card = next(e for e in evs if e.type == EventType.CARD and e.player == player
                and e.attrs["card"] in ("red", "second_yellow"))
    assert not [e for e in evs if e.player == player and (e.period, e.t_ms) > (card.period, card.t_ms)]


def test_crowd_is_steady_two_hertz_and_names_its_trigger(ref):
    _, evs = ref
    for period in (1, 2):
        ts = [e.t_ms for e in evs if e.type == EventType.CROWD and e.period == period]
        assert ts[0] == 0 and {b - a for a, b in zip(ts, ts[1:], strict=False)} == {500}
    crowd = [e for e in evs if e.type == EventType.CROWD]
    assert all(0 <= e.attrs["crowd_level"] <= 1 for e in crowd)
    ids = {e.event_id for e in evs}
    triggers = [e.attrs["trigger_event_id"] for e in crowd if e.attrs["trigger_event_id"]]
    assert triggers and set(triggers) <= ids


def test_tracking_frames_and_running(ref):
    meta, evs = ref
    frames, summary = build_tracking(meta, evs)
    assert frames[0]["frame"] == 0 and len(frames[0]["players"]) == 22
    assert all(0 <= v <= 100 for f in frames for v in f["ball"])
    pairs = zip(frames, frames[1:], strict=False)
    assert all(b["frame"] == a["frame"] + 1 for a, b in pairs if a["period"] == b["period"])
    outfield = [v for pid, v in summary.items() if not pid.endswith(("-01", "-15"))]
    assert max(v["top_speed_kmh"] for v in outfield) <= 34.5  # capped by pace: (7 + 2.5) m/s
    assert 9.5 <= statistics.median(v["distance_km"] for v in outfield) <= 12.5  # docs/CALIBRATION.md range
    assert all(len(f["ball"]) == 3 for f in frames) and max(f["ball"][2] for f in frames) > 3, "lofted passes"


def test_tracking_players_are_at_the_ball_when_they_play_it(ref):
    """The pitch view must show the passer at the ball: players run onto their next touch and arrive on time."""
    from simulator.tracking import _attacks_right, _to_abs

    meta, evs = ref
    frames, _ = build_tracking(meta, evs)
    by_ms = {f["play_ms"]: f for f in frames}
    gaps = []
    for e in evs:
        if e.type in (EventType.PASS, EventType.SHOT_TAKEN, EventType.CARRY) and e.x is not None and e.player:
            f = by_ms.get(e.play_ms // 250 * 250)
            if f and e.player in f["players"]:
                ex, ey = _to_abs(_attacks_right(e.team, meta.home.team_id, e.period), e.x, e.y)
                px, py = f["players"][e.player]
                gaps.append(((px - ex) * 1.05) ** 2 + ((py - ey) * 0.68) ** 2)
    gaps.sort()
    assert gaps[len(gaps) // 2] ** 0.5 < 1.0 and gaps[int(0.9 * len(gaps))] ** 0.5 < 4.0  # metres


def test_tracking_movement_has_no_jumps_and_a_real_shape(ref):
    meta, evs = ref
    frames, _ = build_tracking(meta, evs)
    jolts = ticks = 0
    for a, b, c in zip(frames, frames[1:], frames[2:], strict=False):
        if not a["period"] == b["period"] == c["period"]:
            continue
        for pid, (x, y) in c["players"].items():
            if pid in b["players"] and pid in a["players"]:
                (x1, y1), (x0, y0) = b["players"][pid], a["players"][pid]
                ticks += 1
                jolts += (((x - 2 * x1 + x0) * 1.05) ** 2 + ((y - 2 * y1 + y0) * 0.68) ** 2) ** 0.5 / 0.0625 > 6
    assert jolts / ticks < 0.001, "acceleration over 6 m/s2 (elite players top out around 5-6)"
    team = meta.home.short_name.lower()
    widths = [(max(v[1] for k, v in f["players"].items() if k.startswith(team) and not k.endswith(("-01", "-15")))
               - min(v[1] for k, v in f["players"].items() if k.startswith(team) and not k.endswith(("-01", "-15"))))
              * 0.68 for f in frames[::20]]
    assert 34 <= statistics.median(widths) <= 46, "team width in metres"


def test_calibration_runs():
    rows = calibrate_engine(1000, 3)
    assert {r["key"] for r in rows} >= {"goals", "shots", "passes", "pass_accuracy"}


@pytest.mark.parametrize("story", STORIES, ids=lambda p: p.stem)
def test_committed_reference_files_are_current(story):
    """data/reference/ must equal what the seed generates (regenerate: python -m simulator.cli reference)."""
    from simulator.cli import reference_paths

    meta, events = generate(story)
    lines = [meta.model_dump_json()] + [e.model_dump_json() for e in events]
    assert reference_paths(story)[0].read_text(encoding="utf-8").splitlines() == lines


@pytest.mark.parametrize("seed", [42, 7, 101])
def test_viewer_builds_for_every_reference_match(seed, tmp_path):
    import json

    from simulator.viewer import build_view

    out = tmp_path / f"view-{seed}.html"
    n = build_view(seed, out)
    html = out.read_text(encoding="utf-8")
    assert n > 20_000 and "/*DATA*/null" not in html
    data = json.loads(html.split("const D = ", 1)[1].split(";\n", 1)[0])
    assert data["jumps"] and len(data["frames"]) == n and data["meta"]["homeColor"].startswith("#")

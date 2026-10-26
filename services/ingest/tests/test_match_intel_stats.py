"""Match intelligence from the stats engine (docs/HANDOFF-2026-10-24-match-intelligence.md, section 2)."""

import statistics

import pytest
from crq_schemas import MomentKind
from ingest.derive import KEEP_PER_KIND, PASS_DIFFICULTY, SHOT_SPEED_KMH, difficulty_label, threshold_label
from ingest.stats import SPEED_THRESHOLD_KMH, StateFolder
from simulator.cli import build_meta
from simulator.engine import MatchEngine
from simulator.scripted import DATA_DIR, generate


def _fold(story: str):
    meta, events = generate(DATA_DIR / story)
    folder = StateFolder(meta)
    return folder, [m for ev in events for m in folder.apply(ev)]


@pytest.fixture(scope="module")
def ref():
    return _fold("storyline.json")


def test_pass_quality_for_players_teams_and_the_last_pass(ref):
    folder, _ = ref
    s = folder.state
    for t in (s.home, s.away):
        assert t.pass_accuracy_pct == round(100 * t.passes_completed / t.passes, 1)
        assert 0.3 < t.avg_pass_difficulty < 0.7
    reed = s.players["har-10"]
    assert reed.avg_pass_distance_m > 0 and reed.avg_pass_difficulty > 0
    assert sum(p.hard_passes_completed for p in s.players.values()) > 50
    lp = s.last_pass
    assert lp is not None and lp.difficulty_label == difficulty_label(lp.difficulty)
    passer = s.players[lp.player]
    assert lp.accuracy_pct == round(100 * passer.passes_completed / passer.passes, 1)


def test_shot_speed_on_the_ledger_and_as_maxima(ref):
    folder, _ = ref
    s = folder.state
    assert all(r.speed_kmh for r in s.shots)
    for t in (s.home, s.away):
        assert t.max_shot_speed_kmh == max(r.speed_kmh for r in s.shots if r.team == t.team)
    assert max(p.max_shot_speed_kmh for p in s.players.values()) == max(r.speed_kmh for r in s.shots)


def test_running_distance_comes_from_tracking(ref):
    folder, _ = ref
    assert folder.tracking is not None
    outfield = [p for pid, p in folder.state.players.items() if not pid.endswith(("-01", "-15")) and p.distance_m]
    assert 9_500 <= statistics.median(p.distance_m for p in outfield) <= 12_500
    assert any(p.sprints for p in folder.state.players.values())


def test_no_tracking_means_no_borrowed_distance():
    """A free-play match with the reference seed must not pick up the reference match's running."""
    meta = build_meta(42)
    folder = StateFolder(meta)
    for ev in MatchEngine(meta).run():
        folder.apply(ev)
    assert folder.tracking is None
    assert max(p.distance_m for p in folder.state.players.values()) < 5_000  # carries only
    assert not [t for t in folder.state.thresholds if t.kind == "distance"]


def test_threshold_crossings_are_recorded_and_labelled(ref):
    folder, moments = ref
    kinds = {t.kind for m in moments if m.metrics for t in m.metrics.thresholds}
    assert {"top_speed", "pass_difficulty", "shot_speed"} <= kinds
    final = [t.kind for t in folder.state.thresholds]  # review of #30: distance marks must not evict these
    assert "top_speed" in final and max(final.count(k) for k in set(final)) <= KEEP_PER_KIND
    for m in moments:
        for t in (m.metrics.thresholds if m.metrics else []):
            assert t.value >= t.threshold and t.label == threshold_label(t.value, t.threshold, t.unit)
            assert t.event_id in m.event_ids
    speed = next(m for m in moments if m.kind == MomentKind.SPEED_THRESHOLD)
    top = speed.metrics.thresholds[0]
    assert (top.kind, top.threshold, speed.metrics.player_speed_kmh) == ("top_speed", SPEED_THRESHOLD_KMH, top.value)


@pytest.mark.parametrize("story", ["storyline.json", "storyline_m2.json", "storyline_m3.json"])
def test_standout_passes_are_rare_and_set_up_a_shot(story):
    _, moments = _fold(story)
    standouts = [m for m in moments if m.kind == MomentKind.STANDOUT_PASS]
    assert 1 <= len(standouts) <= 6, "a handful a match, not one per forward pass"
    for m in standouts:
        kp = m.metrics.key_pass
        assert m.importance == 0.4 and kp.key_pass and kp.difficulty >= PASS_DIFFICULTY
        assert kp.difficulty_label == "very_hard" and m.metrics.ball_speed_kmh == kp.ball_speed_kmh


def test_hero_scene_carries_its_key_pass_and_shot_speed(ref):
    _, moments = ref
    hero = next(m for m in moments if m.kind == MomentKind.BIG_CHANCE and m.beat == "result" and "0.38" in m.summary)
    assert hero.metrics.key_pass.player == "har-06" and hero.metrics.key_pass.receiver == "har-10"
    assert hero.metrics.shot_speed_kmh and hero.metrics.player_distance_km > 1
    goal = next(m for m in moments if m.kind == MomentKind.GOAL)
    assert goal.metrics.shot_speed_kmh and goal.metrics.key_pass is None, "a rebound has no pass that set it up"
    fast = [m for m in moments if m.beat in ("chance", "result") and m.metrics and m.metrics.shot_speed_kmh
            and m.metrics.shot_speed_kmh >= SHOT_SPEED_KMH]  # both beats: the live overlay and the card (#43, #65)
    assert all(any(t.kind == "shot_speed" for t in m.metrics.thresholds) for m in fast)


def test_difficulty_bands():
    assert [difficulty_label(d) for d in (0.0, 0.34, 0.35, 0.59, 0.6, 0.79, 0.8, 1.0)] == [
        "routine", "routine", "testing", "testing", "hard", "hard", "very_hard", "very_hard"]


def test_readers_live_with_the_stats_engine():
    import agents.match_intel as agents_intel
    import ingest.intel as ingest_intel

    for name in ("intel_for", "intel_numbers", "team_pass_accuracy"):
        assert getattr(agents_intel, name) is getattr(ingest_intel, name)


def test_shot_records_carry_the_event_detail_and_derived_fields(ref):
    """Who, how, where and how long the move took, for the analyst card and the pitch view's shot markers."""
    from ingest.derive import distance_to_goal

    folder, _ = ref
    meta, events = generate(DATA_DIR / "storyline.json")
    by_id = {e.event_id: e for e in events}
    shots = folder.state.shots
    assert all(r.x is not None and r.y is not None and r.body in ("foot", "header") and r.keeper for r in shots)
    assert all(r.distance_to_goal_m == distance_to_goal(r.x, r.y) for r in shots)
    assert all(r.build_up_ms is not None and r.build_up_ms >= 0 for r in shots)
    assert all(r.blocker for r in shots if r.outcome == "blocked")
    assisted = [r for r in shots if r.assist_event_id]
    assert assisted, "the simulator links each shot to the pass that set it up"
    for r in assisted:
        key_pass = by_id[r.assist_event_id]
        assert key_pass.type == "pass" and key_pass.player == r.assist_by
        assert key_pass.attrs["receiver"] == r.player and key_pass.play_ms <= r.play_ms
    hero = next(r for r in shots if r.xg == 0.38)
    assert (hero.assist_by, hero.keeper, hero.outcome) == ("har-06", "nfu-01", "saved")
    assert 0 < hero.distance_to_goal_m < 16.5 and hero.build_up_ms >= 5 * 2000, "seven-pass build-up"

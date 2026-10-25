"""Small, synthetic-event tests for the match-intelligence rules (review of #30, item 5)."""

from crq_schemas import EventType, MatchEvent, MomentKind
from ingest.derive import KEEP_PER_KIND
from ingest.stats import StateFolder
from simulator.cli import build_meta

META = build_meta(5)
HOME, AWAY = META.home.team_id, META.away.team_id
H = [p.player_id for p in META.home.players if p.position != "GK"]
A = [p.player_id for p in META.away.players if p.position != "GK"]


class FakeTracking:
    """Stands in for the tracking stream: from `at_ms` on, every listed player has run `metres`."""

    def __init__(self, metres: dict[str, float], at_ms: int = 0) -> None:
        self.metres, self.at_ms = metres, at_ms

    def advance(self, play_ms: int) -> dict[str, float]:
        return dict(self.metres) if play_ms >= self.at_ms else {}


def _folder(tracking=None) -> StateFolder:
    return StateFolder(META, tracking=tracking, use_tracking=False)


_seq = iter(range(1, 10_000))


def _ev(type_, t_ms, team, player, phase="ph1", **kw) -> MatchEvent:
    n = next(_seq)
    return MatchEvent(event_id=f"e{n}", match_id=META.match_id, seq=n, play_ms=t_ms, t_ms=t_ms, period=1,
                      type=type_, team=team, player=player, x=kw.pop("x", 60.0), y=kw.pop("y", 50.0),
                      phase_id=phase, **kw)


def _key_pass(t_ms, passer, receiver, difficulty=0.9, phase="ph1"):
    return _ev(EventType.PASS, t_ms, HOME, passer, phase=phase, end_x=85, end_y=50, outcome="success",
               attrs={"receiver": receiver, "distance_m": 25.0, "difficulty": difficulty, "progressive": True,
                      "key_pass": True, "ball_speed_kmh": 52.0})


def _moments(folder, events):
    return [m for e in events for m in folder.apply(e)]


def test_standout_passes_are_at_least_five_minutes_apart_per_team():
    f = _folder()
    ms = _moments(f, [_key_pass(60_000, H[0], H[1]), _key_pass(120_000, H[1], H[2]), _key_pass(361_000, H[2], H[3])])
    standouts = [m for m in ms if m.kind == MomentKind.STANDOUT_PASS]
    assert [m.t_ms for m in standouts] == [60_000, 361_000]
    assert not [m for m in _moments(_folder(), [_key_pass(60_000, H[0], H[1], difficulty=0.7)])
                if m.kind == MomentKind.STANDOUT_PASS], "hard but not very hard"


def test_distance_marks_never_push_out_the_speed_markers():
    everyone = {pid: 10_500.0 for pid in H + A}  # 22 players crossing 5 km and 10 km: 44 crossings
    f = _folder(FakeTracking(everyone, at_ms=3_000))
    _moments(f, [_ev(EventType.CARRY, 1_000, HOME, H[0], attrs={"speed_kmh": 33.0, "distance_m": 10.0}),
                 _ev(EventType.PASS, 3_000, HOME, H[0], outcome="success", attrs={"receiver": H[1]})])
    kinds = [t.kind for t in f.state.thresholds]
    assert "top_speed" in kinds
    assert kinds.count("distance") == KEEP_PER_KIND
    assert [t.play_ms for t in f.state.thresholds] == sorted(t.play_ms for t in f.state.thresholds)


def test_distance_under_a_kilometre_is_never_quoted():
    def chance(metres):
        f = _folder(FakeTracking({H[0]: metres}))
        ms = _moments(f, [_ev(EventType.SHOT_TAKEN, 60_000, HOME, H[0], attrs={"xg": 0.4, "speed_kmh": 90.0})])
        return next(m for m in ms if m.kind == MomentKind.BIG_CHANCE).metrics

    assert chance(300.0).player_distance_km is None
    assert chance(1_500.0).player_distance_km == 1.5


def test_without_tracking_carry_distance_is_never_quoted():
    f = _folder()
    ms = _moments(f, [_ev(EventType.CARRY, 1_000 * i, HOME, H[0], attrs={"speed_kmh": 20.0, "distance_m": 500.0})
                      for i in range(1, 5)]
                  + [_ev(EventType.SHOT_TAKEN, 9_000, HOME, H[0], attrs={"xg": 0.4})])
    assert f.state.players[H[0]].distance_m == 2_000
    assert next(m for m in ms if m.kind == MomentKind.BIG_CHANCE).metrics.player_distance_km is None


def test_build_up_time_starts_with_the_move_the_shot_belongs_to():
    f = _folder()
    _moments(f, [_ev(EventType.PASS, 1_000, HOME, H[0], phase="A", outcome="success", attrs={"receiver": H[1]}),
                 _ev(EventType.PASS, 5_000, HOME, H[1], phase="B", outcome="success", attrs={"receiver": H[2]}),
                 _ev(EventType.SHOT, 9_000, HOME, H[2], phase="B", outcome="saved", attrs={"xg": 0.1}),
                 _ev(EventType.SHOT, 20_000, HOME, H[3], phase=None, outcome="saved", attrs={"xg": 0.1})])
    first, second = sorted(f.state.shots, key=lambda r: r.play_ms)
    assert first.build_up_ms == 4_000, "from the start of move B, not move A"
    assert second.build_up_ms is None, "a shot outside any tracked move"


def test_the_chance_beat_carries_the_shot_speed():
    f = _folder()
    ms = _moments(f, [_ev(EventType.SHOT_TAKEN, 60_000, HOME, H[0], attrs={"xg": 0.4, "speed_kmh": 101.0})])
    chance = next(m for m in ms if m.kind == MomentKind.BIG_CHANCE and m.beat == "chance")
    assert chance.metrics.shot_speed_kmh == 101.0


def test_a_fast_strike_has_its_badge_on_the_chance_beat_and_crosses_once():
    f = _folder()
    ms = _moments(f, [_ev(EventType.SHOT_TAKEN, 60_000, HOME, H[0], attrs={"xg": 0.4, "speed_kmh": 104.0}),
                      _ev(EventType.SHOT, 61_000, HOME, H[0], outcome="saved", attrs={"xg": 0.4, "speed_kmh": 104.0})])
    beats = {m.beat: m for m in ms if m.kind == MomentKind.BIG_CHANCE}
    assert [t.kind for t in beats["chance"].metrics.thresholds] == ["shot_speed"]
    assert beats["result"].metrics.thresholds == [] and beats["result"].metrics.shot_speed_kmh == 104.0
    assert [t.kind for t in f.state.thresholds] == ["shot_speed"]


def test_a_slow_strike_has_no_speed_badge():
    ms = _moments(_folder(), [_ev(EventType.SHOT_TAKEN, 60_000, HOME, H[0], attrs={"xg": 0.4, "speed_kmh": 80.0})])
    assert next(m for m in ms if m.beat == "chance").metrics.thresholds == []


def test_a_fast_goal_from_a_half_chance_keeps_its_badge_on_the_goal():
    f = _folder()
    ms = _moments(f, [_ev(EventType.SHOT_TAKEN, 60_000, HOME, H[0], attrs={"xg": 0.05, "speed_kmh": 110.0}),
                      _ev(EventType.SHOT, 61_000, HOME, H[0], outcome="goal", attrs={"xg": 0.05, "speed_kmh": 110.0})])
    goal = next(m for m in ms if m.kind == MomentKind.GOAL)
    assert [t.kind for t in goal.metrics.thresholds] == ["shot_speed"]
    assert [t.kind for t in f.state.thresholds] == ["shot_speed"]

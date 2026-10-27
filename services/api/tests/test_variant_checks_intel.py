"""Variants may quote the stats engine's match intelligence (speeds, distances, pass ratings), and nothing else."""

from api.variant_checks import build_context, check_variant, unsourced_numbers
from api_factories import match_state, moment, proposal
from crq_schemas import (
    MomentKind,
    MomentMetrics,
    NarrativeVariant,
    OverlayLayer,
    PassQuality,
    ShotRecord,
    TeamStats,
)
from simulator.cli import build_meta

META = build_meta(42)
BASE = "Ade Pike hits 33.1 km/h"
METRICS = MomentMetrics(player="har-09", player_speed_kmh=33.1, shot_speed_kmh=104.2,
                        key_pass=PassQuality(event_id="e-1", team="har", player="har-08", distance_m=38.5,
                                             difficulty=0.82, accuracy_pct=87.0))


def _speed_moment():
    state = match_state(home=TeamStats(team="har", passes=200, passes_completed=170),
                        away=TeamStats(team="nfu", passes=150, passes_completed=120))
    return moment(kind=MomentKind.SPEED_THRESHOLD, state=state, event_ids=["e-1"], metrics=METRICS)


def _failures(text: str, lang: str = "es") -> list[str]:
    m = _speed_moment()
    ctx = build_context(proposal(line=BASE, layer=OverlayLayer.TICKER), m, META)
    v = NarrativeVariant(moment_id="mo-1", persona="analyst", lang=lang, text=text, cites=["e-1"])
    return check_variant(v, ctx)


def test_intel_numbers_may_be_quoted_in_a_variant():
    assert _failures("Ade Pike a 33,1 km/h; disparo a 104,2 km/h; pase de 38,5 m, dificultad 0,82, precisión 87%") == []


def test_a_speed_the_stats_engine_never_produced_fails():
    assert "numbers" in _failures("Ade Pike a 35,4 km/h")


def _team_failures(text: str) -> list[str]:
    state = match_state(home=TeamStats(team="har", passes=250, passes_completed=210, ppda=8.2),
                        away=TeamStats(team="nfu", passes=200, passes_completed=150))
    m = moment(kind=MomentKind.SPEED_THRESHOLD, state=state, event_ids=["e-1"], metrics=METRICS)
    ctx = build_context(proposal(line=BASE, layer=OverlayLayer.TICKER), m, META)
    v = NarrativeVariant(moment_id="mo-1", persona="analyst", lang="es", text=text, cites=["e-1"])
    return check_variant(v, ctx)


def test_team_pass_accuracy_given_to_the_agents_may_be_quoted():
    # The agents receive team_pass_accuracy_pct in their intel input, so quoting it must not be rejected.
    assert _team_failures("Ade Pike a 33,1 km/h; Harbor City pasa al 84%") == []


def test_state_numbers_outside_the_allow_list_still_fail():
    assert "numbers" in _team_failures("Ade Pike a 33,1 km/h; PPDA 8,2")


def test_a_tenth_of_the_difficulty_rating_is_not_an_allowed_number():
    assert "numbers" in _failures("Ade Pike, un pase de dificultad 8")


def test_numbers_in_the_english_line_are_checked_against_the_data():
    m = _speed_moment()
    assert unsourced_numbers("Ade Pike hits 33.1 km/h", m) == []
    assert unsourced_numbers("Ade Pike hits 33 km/h", m) == []  # rounded for fans, still the same speed
    assert unsourced_numbers("Ade Pike nearly 35 km/h, 35 again", m) == ["35"]


def test_no_moment_no_flag():
    assert unsourced_numbers("anything 99", None) == []


def test_the_moment_s_own_shot_xg_is_from_the_data():
    """The template goal card quotes the shot's xG from the moment summary; it must not be flagged (#3 of Oct 27)."""
    shot = ShotRecord(event_id="e-goal", play_ms=0, period=1, t_ms=0, team="har", player="har-09", xg=0.45,
                      outcome="goal", speed_kmh=88.1)
    m = moment(kind=MomentKind.GOAL, event_ids=["e-goal"], state=match_state(shots=[shot]))
    assert unsourced_numbers("GOAL Finn Oakes (foot, xG 0.45)", m) == []
    assert unsourced_numbers("Struck at 88.1 km/h", m) == []
    assert unsourced_numbers("GOAL Finn Oakes (foot, xG 0.54)", m) == ["0.54"]  # another shot's number still flags


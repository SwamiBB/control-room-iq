"""Variants may quote the stats engine's match intelligence (speeds, distances, pass ratings), and nothing else."""

from api.variant_checks import build_context, check_variant
from api_factories import match_state, moment, proposal
from crq_schemas import MomentKind, MomentMetrics, NarrativeVariant, OverlayLayer, PassQuality, TeamStats
from simulator.cli import build_meta

META = build_meta(42)
BASE = "Ade Pike hits 33.1 km/h"
METRICS = MomentMetrics(player="har-09", player_speed_kmh=33.1, shot_speed_kmh=104.2,
                        key_pass=PassQuality(event_id="e-1", team="har", player="har-08", distance_m=38.5,
                                             difficulty=0.82, accuracy_pct=87.0))


def _failures(text: str, lang: str = "es") -> list[str]:
    state = match_state(home=TeamStats(team="har"), away=TeamStats(team="nfu"))
    m = moment(kind=MomentKind.SPEED_THRESHOLD, state=state, event_ids=["e-1"], metrics=METRICS)
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

import pytest
from api.fallback_text import template_line
from api_factories import match_state, moment
from crq_schemas import MomentKind, ShotRecord, TeamStats
from simulator.cli import build_meta

META = build_meta(42)


def _m(kind):
    state = match_state(home=TeamStats(team="har", goals=2), away=TeamStats(team="nfu", goals=1))
    return moment(kind=kind, player="har-02", team="har", state=state)


@pytest.mark.parametrize(("kind", "lang", "expected"), [
    (MomentKind.GOAL, "en", "GOAL! Ade Pike (Harbor City). Score 2–1"),
    (MomentKind.GOAL, "es", "¡GOL! Ade Pike (Harbor City). Marcador 2–1"),
    (MomentKind.GOAL, "hi", "गोल! Ade Pike (Harbor City)। स्कोर 2–1"),
    (MomentKind.BIG_CHANCE, "es", "Gran ocasión de Ade Pike (Harbor City). Marcador 2–1"),
    (MomentKind.CARD, "hi", "Ade Pike (Harbor City) को कार्ड। स्कोर 2–1"),
    (MomentKind.HALF_END, "en", "Half time. Score 2–1"),
    (MomentKind.MATCH_END, "es", "Final del partido. Marcador 2–1"),
])
def test_template_line_fills_names_and_score_from_ground_truth(kind, lang, expected):
    assert template_line(_m(kind), lang, META) == expected


def test_kinds_without_a_template_return_none():
    assert template_line(_m(MomentKind.MOMENTUM_SHIFT), "es", META) is None


def test_unknown_player_keeps_the_id_rather_than_guessing():
    assert template_line(moment(kind=MomentKind.GOAL, player="x-99", team=None), "en", META).startswith("GOAL! x-99")


def _result(outcome: str):
    shot = ShotRecord(event_id="e-1", play_ms=600_000, period=1, t_ms=600_000, team="har", player="har-02", xg=0.68,
                      outcome=outcome)
    state = match_state(home=TeamStats(team="har", goals=2), away=TeamStats(team="nfu", goals=1), shots=[shot])
    return moment(kind=MomentKind.BIG_CHANCE, beat="result", player="har-02", team="har", state=state)


@pytest.mark.parametrize(("outcome", "lang", "expected"), [
    ("saved", "es", "Gran ocasión de Ade Pike (Harbor City), atajada. Marcador 2–1"),
    ("saved", "hi", "Ade Pike (Harbor City) का बड़ा मौका, बचा लिया गया। स्कोर 2–1"),
    ("blocked", "en", "Big chance for Ade Pike (Harbor City), blocked. Score 2–1"),
    ("off_target", "es", "Gran ocasión de Ade Pike (Harbor City), fuera. Marcador 2–1"),
])
def test_a_big_chances_result_says_how_it_ended(outcome, lang, expected):
    assert template_line(_result(outcome), lang, META) == expected


def test_the_strike_and_an_unknown_outcome_keep_the_plain_big_chance_line():
    plain = "Gran ocasión de Ade Pike (Harbor City). Marcador 2–1"
    assert template_line(_m(MomentKind.BIG_CHANCE), "es", META) == plain
    assert template_line(_result("post"), "es", META) == plain

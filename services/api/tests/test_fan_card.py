"""The deaf fan's caption card: built in code from the stats engine's facts, for result beats only."""

from api.fan_card import build_fan_card
from api_factories import match_state, moment
from crq_schemas import MomentKind, ShotRecord, TeamStats
from simulator.cli import build_meta

META = build_meta(42)


def _result(outcome="saved", xg=0.38, beat="result", **overrides):
    shot = ShotRecord(event_id="e-1", play_ms=2_472_600, period=1, t_ms=2_472_600, team="har", player="har-09",
                      xg=xg, outcome=outcome, zone="edge of the box, centre")
    state = match_state(home=TeamStats(team="har", goals=1), away=TeamStats(team="nfu"), shots=[shot])
    return moment(kind=MomentKind.BIG_CHANCE, beat=beat, state=state, event_ids=["e-1"], **overrides)


def test_card_carries_facts_from_the_stats_engine():
    card = build_fan_card(_result(), "Saved! Best chance of the match.", META)
    d = card.detail
    assert (d.zone, d.outcome, d.xg, d.score) == ("edge of the box, centre", "saved", 0.38, "1–0")
    assert d.chance_quality == "about 1 in 3 chances like this go in"
    assert d.shooter == next(p.name for p in META.home.players if p.player_id == "har-09")


def test_caption_is_the_approved_line_and_context_stays_empty():
    card = build_fan_card(_result(), "Saved! Best chance of the match.", META)
    assert card.caption == "Saved! Best chance of the match." and card.lang == "en"
    assert (card.context.past, card.context.now, card.context.next) == (None, None, None)
    assert card.cites == ["e-1"] and card.beat == "result"


def test_only_result_beats_get_a_card():
    assert build_fan_card(_result(beat="chance"), "line", META) is None
    assert build_fan_card(moment(), "line", META) is None  # beat "none"


def test_unknown_outcome_is_left_out_rather_than_guessed():
    assert build_fan_card(_result(outcome="woodwork"), "line", META).detail.outcome is None


def test_a_moment_without_its_shot_still_gets_names_and_score():
    m = _result()
    m.state.shots = []
    d = build_fan_card(m, "line", META).detail
    assert d.zone is None and d.xg is None and d.chance_quality is None and d.score == "1–0"

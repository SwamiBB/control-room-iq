"""The goal routine: lead graphic + scorer stats + ticker, grouped as one package."""

import re
from datetime import UTC, datetime

from api.goal_package import (
    REPLAY_WINDOW_MS,
    analyst_stats_line,
    build_goal_package,
    code_built_lines,
    code_built_persona_lines,
    is_code_built,
    stats_line,
    ticker_line,
)
from api.packets import packet_slot
from api_factories import match_state, moment, proposal
from crq_schemas import MatchMeta, MomentKind, OverlayLayer, Persona, Player, PlayerStats, Team, TeamStats


def _meta() -> MatchMeta:
    def team(tid, name, color, pid, pname):
        return Team(team_id=tid, name=name, short_name=tid.upper(), primary_color=color, formation="4-3-3",
                    players=[Player(player_id=pid, name=pname, number=9, position="FW", pace=.7, passing=.6,
                                    shooting=.8, defending=.3)])
    return MatchMeta(match_id="m", venue="Harbor Park", kickoff_utc=datetime(2026, 10, 24, 14, tzinfo=UTC),
                     home=team("har", "Harbor City", "#0b3d91", "har-09", "Finn Oakes"),
                     away=team("nor", "Northfield United", "#b22222", "nor-09", "Rafe Cole"), seed=42)


def _goal(**overrides):
    state = match_state(home=TeamStats(team="har", goals=1), away=TeamStats(team="nor"),
                        players={"har-09": PlayerStats(player_id="har-09", team="har", goals=1, shots=3, xg=0.83)})
    return moment(kind=MomentKind.GOAL, importance=1.0, t_ms=2_474_000, state=state, **overrides)


def _lead():
    return proposal("p-goal", layer=OverlayLayer.FULL_SCREEN, line="GOAL. Oakes scores the rebound.",
                    t_start_ms=2_476_000, t_end_ms=2_494_000, priority=1)


def test_a_goal_becomes_a_three_item_package_in_running_order():
    items = build_goal_package(_lead(), _goal(), _meta())
    assert [p.item_label for p in items] == ["Goal graphic", "Scorer stats", "Ticker"]
    assert [p.package_seq for p in items] == [0, 1, 2]
    assert len({p.package_id for p in items}) == 1 and items[0].package_id == "pk-p-goal"
    assert [p.layer for p in items] == [OverlayLayer.FULL_SCREEN, OverlayLayer.LOWER_THIRD, OverlayLayer.TICKER]


def test_only_the_lead_carries_ai_text():
    lead, stats, ticker = build_goal_package(_lead(), _goal(), _meta())
    assert lead.line == "GOAL. Oakes scores the rebound." and not is_code_built(lead)
    assert is_code_built(stats) and is_code_built(ticker)


def test_follow_ups_are_built_from_the_official_stats():
    m, meta = _goal(), _meta()
    assert stats_line(m, meta) == "Finn Oakes · 1 goal · 3 shots · xG 0.83 today"
    assert ticker_line(m, meta) == "GOAL 42' · Harbor City 1–0 Northfield United · Finn Oakes"


def test_follow_ups_in_spanish_and_hindi_change_only_the_words():
    m, meta = _goal(), _meta()
    assert stats_line(m, meta, "es") == "Finn Oakes · 1 gol · 3 remates · xG 0.83 hoy"
    assert stats_line(m, meta, "hi") == "Finn Oakes आज · 1 गोल · 3 शॉट · xG 0.83"
    assert ticker_line(m, meta, "es") == "GOL 42' · Harbor City 1–0 Northfield United · Finn Oakes"
    assert ticker_line(m, meta, "hi") == "गोल 42' · Harbor City 1–0 Northfield United · Finn Oakes"


def test_spanish_counts_take_the_plural():
    state = match_state(home=TeamStats(team="har", goals=2), away=TeamStats(team="nor"),
                        players={"har-09": PlayerStats(player_id="har-09", team="har", goals=2, shots=1, xg=0.5)})
    m = moment(kind=MomentKind.GOAL, importance=1.0, t_ms=2_474_000, state=state)
    assert stats_line(m, _meta(), "es") == "Finn Oakes · 2 goles · 1 remate · xG 0.50 hoy"


def test_every_language_quotes_the_same_numbers_and_names():
    m, meta = _goal(), _meta()
    _, stats, ticker = build_goal_package(_lead(), m, meta)
    for item in (stats, ticker):
        lines = code_built_lines(item, m, meta)
        assert set(lines) == {"es", "hi"}
        for line in lines.values():
            assert re.findall(r"[\d.–']+", line) == re.findall(r"[\d.–']+", item.line)
            assert "Finn Oakes" in line


def _goal_with_match_stats():
    ps = PlayerStats(player_id="har-09", team="har", goals=1, shots=3, xg=0.61, passes=18, passes_completed=15,
                     distance_m=5419.9, sprints=6)
    state = match_state(home=TeamStats(team="har", goals=1), away=TeamStats(team="nor"), players={"har-09": ps})
    return moment(kind=MomentKind.GOAL, importance=1.0, t_ms=2_474_000, state=state)


def test_the_analyst_gets_the_scorers_match_numbers_in_every_language():
    m, meta = _goal_with_match_stats(), _meta()
    assert analyst_stats_line(m, meta) == ("Finn Oakes today · 1 goal · 3 shots · xG 0.61 · 15/18 passes · 5.42 km"
                                           " · 6 sprints")
    assert analyst_stats_line(m, meta, "es") == ("Finn Oakes hoy · 1 gol · 3 remates · xG 0.61 · 15/18 pases · 5.42 km"
                                                 " · 6 sprints")
    assert analyst_stats_line(m, meta, "hi") == ("Finn Oakes आज · 1 गोल · 3 शॉट · xG 0.61 · 15/18 पास · 5.42 km"
                                                 " · 6 स्प्रिंट")


def test_the_analyst_line_leaves_out_what_the_engine_has_not_counted():
    # _goal() has no passes, distance or sprints: zeros are left out, never shown as "0/0 passes".
    assert analyst_stats_line(_goal(), _meta()) == "Finn Oakes today · 1 goal · 3 shots · xG 0.83"


def test_only_the_scorer_stats_carry_an_analyst_line():
    m, meta = _goal_with_match_stats(), _meta()
    lead, stats, ticker = build_goal_package(_lead(), m, meta)
    lines = code_built_persona_lines(stats, m, meta)
    assert set(lines) == {(Persona.ANALYST, lang) for lang in ("en", "es", "hi")}
    assert code_built_persona_lines(lead, m, meta) == {} == code_built_persona_lines(ticker, m, meta)
    assert code_built_persona_lines(stats, None, meta) == {}


def test_the_scorer_stats_carry_the_scorers_side_not_a_colour():
    _, stats, _ = build_goal_package(_lead(), _goal(), _meta())
    assert stats.payload["team_side"] == "home" and "team_color" not in stats.payload
    _, away_stats, _ = build_goal_package(_lead(), _goal(team="nor", player="nor-09"), _meta())
    assert away_stats.payload["team_side"] == "away"


def test_no_language_lines_for_the_lead_or_without_the_moment():
    m, meta = _goal(), _meta()
    lead, stats, _ = build_goal_package(_lead(), m, meta)
    assert code_built_lines(lead, m, meta) == {} and code_built_lines(stats, None, meta) == {}


def test_scorer_stats_wait_for_the_replay_window():
    _, stats, ticker = build_goal_package(_lead(), _goal(), _meta())
    fired_at = 2_480_000
    assert packet_slot(stats, fired_at)[0] == fired_at + REPLAY_WINDOW_MS
    assert packet_slot(ticker, fired_at)[0] == fired_at


def test_other_moments_are_not_packaged():
    lead = _lead()
    assert build_goal_package(lead, moment(), _meta()) == [lead]
    assert lead.package_id is None


def test_stats_line_uses_singular_for_one_shot():
    m = _goal()
    m.state.players["har-09"].shots = 1
    assert stats_line(m, _meta()) == "Finn Oakes · 1 goal · 1 shot · xG 0.83 today"

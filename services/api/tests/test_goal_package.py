"""The goal routine: lead graphic + scorer stats + ticker, grouped as one package."""

from datetime import UTC, datetime

from api.goal_package import (
    REPLAY_WINDOW_MS,
    build_goal_package,
    is_code_built,
    stats_line,
    ticker_line,
)
from api.packets import packet_slot
from api_factories import match_state, moment, proposal
from crq_schemas import MatchMeta, MomentKind, OverlayLayer, Player, PlayerStats, Team, TeamStats


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

"""The goal routine: one decision fires the goal graphic, the scorer's stats and the ticker line.

At a goal the gallery has the most to do at once. The producer agent proposes the lead graphic; this
module adds the two follow-ups the gallery always runs, built in code from the official stats, and
groups all three as one package so the graphics operator fires them with one click.

Pure functions: no I/O, no clock reads, no model calls. Only the lead item carries AI text.
"""

from __future__ import annotations

from crq_schemas import MatchMeta, Moment, MomentKind, OverlayLayer, OverlayProposal, Team

# Play-time delays after the package is fired. The scorer's stats wait for the replay sequence to end.
REPLAY_WINDOW_MS = 25_000
STATS_HOLD_MS = 10_000
TICKER_HOLD_MS = 45_000

LEAD_LABEL = "Goal graphic"
STATS_LABEL = "Scorer stats"
TICKER_LABEL = "Ticker"


def _team(team_id: str | None, meta: MatchMeta | None) -> Team | None:
    teams = (meta.home, meta.away) if meta else ()
    return next((t for t in teams if t.team_id == team_id), None)


def _player_name(player_id: str | None, meta: MatchMeta | None) -> str:
    players = [p for t in ((meta.home, meta.away) if meta else ()) for p in t.players]
    return next((p.name for p in players if p.player_id == player_id), player_id or "")


def _minute(m: Moment) -> int:
    return m.t_ms // 60_000 + (45 if m.period == 2 else 0) + 1


def stats_line(m: Moment, meta: MatchMeta | None) -> str:
    ps = m.state.players.get(m.player or "")
    name = _player_name(m.player, meta)
    if ps is None:
        return name
    goals = f"{ps.goals} goal" + ("" if ps.goals == 1 else "s")
    return f"{name} · {goals} · {ps.shots} shots · xG {ps.xg:.2f} today"


def ticker_line(m: Moment, meta: MatchMeta | None) -> str:
    home, away = (meta.home.name, meta.away.name) if meta else (m.state.home.team, m.state.away.team)
    scorer = _player_name(m.player, meta)
    return (f"GOAL {_minute(m)}' · {home} {m.state.home.goals}–{m.state.away.goals} {away}"
            + (f" · {scorer}" if scorer else ""))


def _follow_up(lead: OverlayProposal, seq: int, label: str, layer: OverlayLayer, line: str, offset_ms: int,
               hold_ms: int, payload: dict) -> OverlayProposal:
    return OverlayProposal(
        proposal_id=f"{lead.proposal_id}-{seq}", match_id=lead.match_id, moment_id=lead.moment_id, layer=layer,
        t_start_ms=lead.t_start_ms + offset_ms, t_end_ms=lead.t_start_ms + offset_ms + hold_ms, line=line,
        payload=payload | {"source": "code"}, priority=lead.priority, evidence=lead.evidence,
        reasoning=f"{label}: built in code from the official stats, part of the goal routine.",
        proposed_at=lead.proposed_at, package_id=lead.package_id, package_seq=seq, package_offset_ms=offset_ms,
        item_label=label)


def build_goal_package(lead: OverlayProposal, m: Moment, meta: MatchMeta | None) -> list[OverlayProposal]:
    """The lead proposal plus its follow-ups, all sharing one package_id. Non-goals pass through alone."""
    if m.kind != MomentKind.GOAL:
        return [lead]
    lead = lead.model_copy(update={"package_id": f"pk-{lead.proposal_id}", "package_seq": 0,
                                   "package_offset_ms": 0, "item_label": LEAD_LABEL})
    team = _team(m.team, meta)
    color = {"team_color": team.primary_color} if team else {}
    stats = _follow_up(lead, 1, STATS_LABEL, OverlayLayer.LOWER_THIRD, stats_line(m, meta), REPLAY_WINDOW_MS,
                       STATS_HOLD_MS, {"player_id": m.player} | color)
    ticker = _follow_up(lead, 2, TICKER_LABEL, OverlayLayer.TICKER, ticker_line(m, meta), 0, TICKER_HOLD_MS,
                        {"score": [m.state.home.goals, m.state.away.goals]})
    return [lead, stats, ticker]


def is_code_built(p: OverlayProposal) -> bool:
    """Follow-up items carry no AI text, so no AI variants exist for them."""
    return p.package_seq > 0 and p.payload.get("source") == "code"

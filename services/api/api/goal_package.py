"""The goal routine: one decision fires the goal graphic, the scorer's stats and the ticker line.

At a goal the gallery has the most to do at once. The producer agent proposes the lead graphic; this
module adds the two follow-ups the gallery always runs, built in code from the official stats, and
groups all three as one package so the graphics operator fires them with one click.

Pure functions: no I/O, no clock reads, no model calls. Only the lead item carries AI text; the follow-ups are
built in English, Spanish and Hindi from the same stats.
"""

from __future__ import annotations

from typing import NamedTuple

from crq_schemas import MatchMeta, Moment, MomentKind, OverlayLayer, OverlayProposal, Persona

# Play-time delays after the package is fired. The scorer's stats wait for the replay sequence to end.
REPLAY_WINDOW_MS = 25_000
STATS_HOLD_MS = 10_000
TICKER_HOLD_MS = 45_000

LEAD_LABEL = "Goal graphic"
STATS_LABEL = "Scorer stats"
TICKER_LABEL = "Ticker"


def _side(team_id: str | None, meta: MatchMeta | None) -> str | None:
    """"home" or "away" for a team, so a graphic about it takes the same side colour as the score bug."""
    if not meta or not team_id:
        return None
    return "home" if team_id == meta.home.team_id else "away" if team_id == meta.away.team_id else None


def _player_name(player_id: str | None, meta: MatchMeta | None) -> str:
    players = [p for t in ((meta.home, meta.away) if meta else ()) for p in t.players]
    return next((p.name for p in players if p.player_id == player_id), player_id or "")


def match_minute(m: Moment) -> int:
    """The minute on the ticker ("GOAL 42'"); the goal templates quote the same one."""
    return m.t_ms // 60_000 + (45 if m.period == 2 else 0) + 1


# The words of the two code-built lines in each language: (singular, plural) for counted nouns. Numbers, names and
# the score are the same in every language; only these words change (native-speaker review wanted, as for the
# templates in fallback_text.py).
class _Words(NamedTuple):
    head: str  # the scorer's name; Hindi puts "today" here, so it covers the whole line rather than only the xG
    goal_caps: str
    goal: tuple[str, str]
    shot: tuple[str, str]
    xg_today: str
    # The analyst's longer line: "{name} today" heads it, then passes completed of attempted, and sprints
    today: str
    passes: str
    sprint: tuple[str, str]


_WORDS: dict[str, _Words] = {
    "en": _Words("{name}", "GOAL", ("goal", "goals"), ("shot", "shots"), "xG {xg} today",
                 "{name} today", "{done}/{tried} passes", ("sprint", "sprints")),
    "es": _Words("{name}", "GOL", ("gol", "goles"), ("remate", "remates"), "xG {xg} hoy",
                 "{name} hoy", "{done}/{tried} pases", ("sprint", "sprints")),
    "hi": _Words("{name} आज", "गोल", ("गोल", "गोल"), ("शॉट", "शॉट"), "xG {xg}",
                 "{name} आज", "{done}/{tried} पास", ("स्प्रिंट", "स्प्रिंट")),
}


def _count(n: int, noun: tuple[str, str]) -> str:
    return f"{n} {noun[0] if n == 1 else noun[1]}"


def stats_line(m: Moment, meta: MatchMeta | None, lang: str = "en") -> str:
    words = _WORDS[lang]
    ps = m.state.players.get(m.player or "")
    name = _player_name(m.player, meta)
    if ps is None:
        return name
    xg = words.xg_today.format(xg=f"{ps.xg:.2f}")
    return f"{words.head.format(name=name)} · {_count(ps.goals, words.goal)} · {_count(ps.shots, words.shot)} · {xg}"


def analyst_stats_line(m: Moment, meta: MatchMeta | None, lang: str = "en") -> str:
    """The analyst's scorer stats: the same goals, shots and xG, plus the match's passing, distance and sprints.
    Only what the stats engine has for this match (no season figures), and a zero is left out rather than shown."""
    words = _WORDS[lang]
    ps = m.state.players.get(m.player or "")
    name = _player_name(m.player, meta)
    if ps is None:
        return name
    parts = [words.today.format(name=name), _count(ps.goals, words.goal), _count(ps.shots, words.shot),
             f"xG {ps.xg:.2f}"]
    if ps.passes:
        parts.append(words.passes.format(done=ps.passes_completed, tried=ps.passes))
    if ps.distance_m:
        parts.append(f"{ps.distance_m / 1000:.2f} km")
    if ps.sprints:
        parts.append(_count(ps.sprints, words.sprint))
    return " · ".join(parts)


def ticker_line(m: Moment, meta: MatchMeta | None, lang: str = "en") -> str:
    home, away = (meta.home.name, meta.away.name) if meta else (m.state.home.team, m.state.away.team)
    scorer = _player_name(m.player, meta)
    return (f"{_WORDS[lang].goal_caps} {match_minute(m)}' · {home} {m.state.home.goals}–{m.state.away.goals} {away}"
            + (f" · {scorer}" if scorer else ""))


def code_built_lines(p: OverlayProposal, m: Moment | None, meta: MatchMeta | None) -> dict[str, str]:
    """A follow-up's line in each language other than English, from the same stats as the English line. They go
    out by the template path (delivery.py), so a Spanish or Hindi viewer reads them in their own language."""
    line = {1: stats_line, 2: ticker_line}.get(p.package_seq)
    if m is None or line is None:
        return {}
    return {lang: line(m, meta, lang) for lang in _WORDS if lang != "en"}


def code_built_persona_lines(p: OverlayProposal, m: Moment | None,
                             meta: MatchMeta | None) -> dict[tuple[Persona, str], str]:
    """The analyst's own scorer stats in every language, English included (delivery.py prefers a persona's line)."""
    if m is None or p.package_seq != 1:
        return {}
    return {(Persona.ANALYST, lang): analyst_stats_line(m, meta, lang) for lang in _WORDS}


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
    side = {"team_side": s} if (s := _side(m.team, meta)) else {}
    stats = _follow_up(lead, 1, STATS_LABEL, OverlayLayer.LOWER_THIRD, stats_line(m, meta), REPLAY_WINDOW_MS,
                       STATS_HOLD_MS, {"player_id": m.player} | side)
    ticker = _follow_up(lead, 2, TICKER_LABEL, OverlayLayer.TICKER, ticker_line(m, meta), 0, TICKER_HOLD_MS,
                        {"score": [m.state.home.goals, m.state.away.goals]})
    return [lead, stats, ticker]


def is_code_built(p: OverlayProposal) -> bool:
    """Follow-up items carry no AI text, so no AI variants exist for them."""
    return p.package_seq > 0 and p.payload.get("source") == "code"

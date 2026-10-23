"""The deaf fan's caption card for a result beat (a big chance's outcome, or a goal), built in code.

The caption itself is the approved line, and each viewer already receives it in their language through
the normal delivery (checked variant, then template, then the English line): the viewer renders the
packet's `line` as the caption. Everything else on the card is fact from the stats engine (who, where,
what happened, how good the chance was, the score), so it carries no AI text and the viewer renders it
in the viewer's language from a fixed table. No free-text context yet: the catch-up card covers that.

Pure functions: no I/O, no clock reads, no model calls.
"""

from __future__ import annotations

from crq_schemas import FanCard, FanDetail, MatchMeta, Moment

# Outcome codes as the simulator writes them; the viewer translates these, not free text.
OUTCOMES = ("goal", "saved", "off_target", "blocked")


def _player_name(player_id: str | None, meta: MatchMeta | None) -> str | None:
    if not player_id:
        return None
    players = [p for t in ((meta.home, meta.away) if meta else ()) for p in t.players]
    return next((p.name for p in players if p.player_id == player_id), player_id)


def chance_quality(xg: float) -> str:
    """English wording for the chance; the same rule the viewer applies in Spanish and Hindi."""
    from ingest.derive import chance_quality as rule  # the stats engine's wording, not a second copy

    return rule(xg)


def build_fan_card(m: Moment, line: str, meta: MatchMeta | None) -> FanCard | None:
    """A card for result beats only; the strike itself is the FanCue, which airs before any decision."""
    if m.beat != "result":
        return None
    shot = next((s for s in m.state.shots if s.event_id in m.event_ids), None)
    detail = FanDetail(shooter=_player_name(m.player, meta),
                       zone=shot.zone or None if shot else None,
                       outcome=shot.outcome if shot and shot.outcome in OUTCOMES else None,
                       xg=shot.xg if shot else None,
                       chance_quality=chance_quality(shot.xg) if shot else None,
                       score=f"{m.state.home.goals}–{m.state.away.goals}")
    return FanCard(card_id=f"fc-{m.moment_id}", match_id=m.match_id, moment_id=m.moment_id, beat="result",
                   play_ms=m.play_ms, lang="en", caption=line, detail=detail, cites=list(m.event_ids))

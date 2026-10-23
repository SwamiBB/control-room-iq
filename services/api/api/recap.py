"""Catch-up card data for a viewer who just joined: what happened in the last N minutes of play."""

from __future__ import annotations

from crq_schemas import MatchState, Recap

MINUTE_MS = 60_000
RECAP_WINDOWS = (10, 20, 30)  # minutes, as in RecapRequest.minutes


def build_recap(state: MatchState, minutes: int, now_play_ms: int) -> Recap:
    """Deterministic points only. `text` stays empty: a generated summary belongs to the agents and,
    like any AI text, would need the operator gate before it airs."""
    start = max(0, now_play_ms - minutes * MINUTE_MS)
    points = [p for p in state.recap_points if start <= p.play_ms <= now_play_ms]
    return Recap(match_id=state.match_id, from_play_ms=start, to_play_ms=now_play_ms,
                 score=f"{state.home.goals}-{state.away.goals}", points=points, text="")

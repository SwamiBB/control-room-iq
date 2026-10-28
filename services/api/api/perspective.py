"""Supporter framing: the match from the viewer's side, built from state and string tables only.

No generated text, so it needs no operator approval and works in every language the same way. It is
added to the per-viewer packet's payload; the approved `line` is never changed.
"""

from __future__ import annotations

from typing import Literal

from crq_schemas import Lang, MatchMeta, MatchState

from .packets import ViewerPrefs

Standing = Literal["up", "down", "level"]

# Native-speaker review wanted for es/hi before broadcast.
_SCORE_TEXT: dict[str, dict[Standing, str]] = {
    "en": {"up": "{us}–{them} up", "down": "{us}–{them} down", "level": "level at {us}–{them}"},
    "es": {"up": "ganando {us}–{them}", "down": "perdiendo {us}–{them}", "level": "empatando {us}–{them}"},
    "hi": {"up": "{us}–{them} से आगे", "down": "{us}–{them} से पीछे", "level": "{us}–{them} से बराबर"},
}


def score_text(ours: int, theirs: int, lang: Lang) -> str:
    standing: Standing = "up" if ours > theirs else "down" if ours < theirs else "level"
    return _SCORE_TEXT[lang][standing].format(us=ours, them=theirs)


def perspective(state: MatchState, prefs: ViewerPrefs, meta: MatchMeta | None) -> dict | None:
    """`payload.perspective` for a supporter, or None for a neutral viewer."""
    if prefs.allegiance == "neutral":
        return None
    is_home = prefs.allegiance == "home"
    ours, theirs = (state.home, state.away) if is_home else (state.away, state.home)
    team = (meta.home if is_home else meta.away) if meta else None
    return {"side": prefs.allegiance, "team": ours.team, "color": team.primary_color if team else None,
            "score": [ours.goals, theirs.goals], "score_text": score_text(ours.goals, theirs.goals, prefs.lang)}

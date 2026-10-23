"""Per-language template lines built from ground truth, for viewers whose AI variant may not air.

Deterministic text from the moment's own state, so it needs no operator approval. It always states the
score, which also satisfies the deaf-access rule. Native-speaker review wanted for es/hi before broadcast.
"""

from __future__ import annotations

from crq_schemas import Lang, MatchMeta, Moment, MomentKind

_TEMPLATES: dict[MomentKind, dict[str, str]] = {
    MomentKind.GOAL: {"en": "GOAL! {player} ({team}). Score {score}",
                      "es": "¡GOL! {player} ({team}). Marcador {score}",
                      "hi": "गोल! {player} ({team})। स्कोर {score}"},
    MomentKind.BIG_CHANCE: {"en": "Big chance for {player} ({team}). Score {score}",
                            "es": "Gran ocasión de {player} ({team}). Marcador {score}",
                            "hi": "{player} ({team}) का बड़ा मौका। स्कोर {score}"},
    MomentKind.CARD: {"en": "Card for {player} ({team}). Score {score}",
                      "es": "Tarjeta para {player} ({team}). Marcador {score}",
                      "hi": "{player} ({team}) को कार्ड। स्कोर {score}"},
    MomentKind.HALF_END: {"en": "Half time. Score {score}", "es": "Descanso. Marcador {score}",
                          "hi": "हाफ़ टाइम। स्कोर {score}"},
    MomentKind.MATCH_END: {"en": "Full time. Score {score}", "es": "Final del partido. Marcador {score}",
                           "hi": "फ़ुल टाइम। स्कोर {score}"},
}


def _player_name(player_id: str | None, meta: MatchMeta | None) -> str:
    # Names are never translated or transliterated; an unknown id is shown as-is rather than guessed.
    players = [p for t in (meta.home, meta.away) for p in t.players] if meta else []
    return next((p.name for p in players if p.player_id == player_id), player_id or "")


def _team_name(team_id: str | None, meta: MatchMeta | None) -> str:
    teams = (meta.home, meta.away) if meta else ()
    return next((t.name for t in teams if t.team_id == team_id), team_id or "")


def template_line(m: Moment, lang: Lang, meta: MatchMeta | None) -> str | None:
    template = _TEMPLATES.get(m.kind, {}).get(lang)
    if template is None:
        return None
    score = f"{m.state.home.goals}–{m.state.away.goals}"
    return template.format(player=_player_name(m.player, meta), team=_team_name(m.team, meta), score=score)

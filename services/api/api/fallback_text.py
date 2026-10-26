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


# A big chance's result beat says how it ended, as the English line does ("Big chance Kai Reed saved"): with
# the strike's template it read the same before and after the save on Spanish and Hindi screens (#54).
_BIG_CHANCE_RESULTS: dict[str, dict[str, str]] = {
    "saved": {"en": "Big chance for {player} ({team}), saved. Score {score}",
              "es": "Gran ocasión de {player} ({team}), atajada. Marcador {score}",
              "hi": "{player} ({team}) का बड़ा मौका, बचा लिया गया। स्कोर {score}"},
    "blocked": {"en": "Big chance for {player} ({team}), blocked. Score {score}",
                "es": "Gran ocasión de {player} ({team}), bloqueada. Marcador {score}",
                "hi": "{player} ({team}) का बड़ा मौका, ब्लॉक कर दिया गया। स्कोर {score}"},
    "off_target": {"en": "Big chance for {player} ({team}), off target. Score {score}",
                   "es": "Gran ocasión de {player} ({team}), fuera. Marcador {score}",
                   "hi": "{player} ({team}) का बड़ा मौका, निशाने से बाहर। स्कोर {score}"},
}


def _shot_outcome(m: Moment) -> str | None:
    """How the moment's own shot ended, from the stats engine's shot ledger (as the fan card reads it)."""
    shot = next((s for s in m.state.shots if s.event_id in m.event_ids), None)
    return shot.outcome if shot else None


def _player_name(player_id: str | None, meta: MatchMeta | None) -> str:
    # Names are never translated or transliterated; an unknown id is shown as-is rather than guessed.
    players = [p for t in (meta.home, meta.away) for p in t.players] if meta else []
    return next((p.name for p in players if p.player_id == player_id), player_id or "")


def _team_name(team_id: str | None, meta: MatchMeta | None) -> str:
    teams = (meta.home, meta.away) if meta else ()
    return next((t.name for t in teams if t.team_id == team_id), team_id or "")


def template_line(m: Moment, lang: Lang, meta: MatchMeta | None) -> str | None:
    template = _TEMPLATES.get(m.kind, {}).get(lang)
    if m.kind == MomentKind.BIG_CHANCE and m.beat == "result":
        template = _BIG_CHANCE_RESULTS.get(_shot_outcome(m) or "", {}).get(lang, template)
    if template is None:
        return None
    score = f"{m.state.home.goals}–{m.state.away.goals}"
    return template.format(player=_player_name(m.player, meta), team=_team_name(m.team, meta), score=score)

"""Per-language template lines built from ground truth, for viewers whose AI variant may not air.

Deterministic text from the moment's own state, so it needs no operator approval. It always states the
score, which also satisfies the deaf-access rule. Native-speaker review wanted for es/hi before broadcast.
"""

from __future__ import annotations

from crq_schemas import Lang, MatchMeta, Moment, MomentKind, Persona, ShotRecord

from .goal_package import match_minute

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


# A goal's Spanish and Hindi line for each persona, in place of the one shared line above (goals always go out as a
# template in those languages: delivery.py). The same facts as the English template, plus the ticker's minute; the
# analyst also gets the shot's xG, which the deaf fan's card shows. Nothing else: no adjectives about the goal.
_GOAL_BY_PERSONA: dict[Persona, dict[str, str]] = {
    Persona.NEWCOMER: {"es": "¡GOL! {player} marca para {team}. Marcador: {score}",
                       "hi": "गोल! {player} ने {team} के लिए गोल किया। स्कोर: {score}"},
    Persona.FAN: {"es": "¡GOL de {player} para {team} en el minuto {minute}! Marcador {score}",
                  "hi": "गोल! {minute}वें मिनट में {player} ने {team} के लिए गोल किया! स्कोर {score}"},
    Persona.ANALYST: {"es": "Gol de {player} ({team}), minuto {minute}{xg}. Marcador {score}",
                      "hi": "गोल: {player} ({team}), {minute}वाँ मिनट{xg}। स्कोर {score}"},
}


_SHOT_XG = {"es": ", xG del remate {xg}", "hi": ", शॉट का xG {xg}"}


def moment_shot(m: Moment) -> ShotRecord | None:
    """The moment's own shot in the stats engine's shot ledger: the template line, the fan card and the number check
    all read this one."""
    return next((s for s in m.state.shots if s.event_id in m.event_ids), None)


def _shot_outcome(m: Moment) -> str | None:
    """How the moment's own shot ended."""
    shot = moment_shot(m)
    return shot.outcome if shot else None


def _player_name(player_id: str | None, meta: MatchMeta | None) -> str:
    # Names are never translated or transliterated; an unknown id is shown as-is rather than guessed.
    players = [p for t in (meta.home, meta.away) for p in t.players] if meta else []
    return next((p.name for p in players if p.player_id == player_id), player_id or "")


def _team_name(team_id: str | None, meta: MatchMeta | None) -> str:
    teams = (meta.home, meta.away) if meta else ()
    return next((t.name for t in teams if t.team_id == team_id), team_id or "")


def template_line(m: Moment, lang: Lang, meta: MatchMeta | None, persona: Persona | None = None) -> str | None:
    """The line for a viewer in `lang`; a persona gets its own goal line in Spanish and Hindi, else the shared one."""
    template = _TEMPLATES.get(m.kind, {}).get(lang)
    if m.kind == MomentKind.GOAL and persona is not None:
        template = _GOAL_BY_PERSONA[persona].get(lang, template)
    if m.kind == MomentKind.BIG_CHANCE and m.beat == "result":
        template = _BIG_CHANCE_RESULTS.get(_shot_outcome(m) or "", {}).get(lang, template)
    if template is None:
        return None
    score = f"{m.state.home.goals}–{m.state.away.goals}"
    shot = moment_shot(m)
    # The shot's own xG, named as such: the scorer's stats a moment later show his match total.
    xg = _SHOT_XG.get(lang, ", xG {xg}").format(xg=f"{shot.xg:.2f}") if shot and shot.xg is not None else ""
    return template.format(player=_player_name(m.player, meta), team=_team_name(m.team, meta), score=score,
                           minute=match_minute(m), xg=xg)

"""Code checks an AI persona/access/language variant must pass before it airs.

The operator approves the meaning once, in the base language; these checks are what lets a variant of
that line air in a language the operator may not read. They catch invented numbers, changed or added
names, citations outside the moment, overlong text, banned topics, low faithfulness, and text that was
never translated. Pure functions: no I/O and no model calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agents.match_intel import intel_for, intel_numbers, team_pass_accuracy
from crq_schemas import MatchMeta, MatchState, Moment, NarrativeVariant, OverlayLayer, OverlayProposal

BASE_LANG = "en"  # language of the proposal line the operator approves
FAITHFULNESS_MIN = 0.8
DEVANAGARI_MIN_SHARE = 0.3

# Agree with the renderer; deliberately generous so normal es/hi expansion (~25%) fits.
LAYER_MAX_CHARS = {OverlayLayer.LOWER_THIRD: 90, OverlayLayer.STAT_PANEL: 90, OverlayLayer.HEATMAP: 90,
                   OverlayLayer.TICKER: 140, OverlayLayer.FULL_SCREEN: 120, OverlayLayer.CAPTION: 160,
                   OverlayLayer.PLAYER_TAG: 40, OverlayLayer.PITCH_OVERLAY: 60}

_BANNED = (re.compile(r"\b(referee|ref|odds|bet|betting|bookmakers?|injur(?:y|ed|ies)(?!\s+time))\b", re.I),
           re.compile(r"\b(árbitro|arbitral|apuestas?|cuotas?|lesi[oó]n|lesionad[oa])\b", re.I),
           re.compile(r"रेफरी|सट्टा|चोट"))
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LETTER = re.compile(r"[^\W\d_]")


@dataclass(frozen=True)
class CheckContext:
    base_line: str
    allowed_numbers: tuple[float, ...]
    required_players: tuple[tuple[str, str], ...]  # (full name, surname) named in the approved line
    other_players: tuple[str, ...]  # names that must not appear: full names, plus surnames unique in the match
    cited: frozenset[str]  # empty when the moment is unknown, which skips the citation check
    max_chars: int


# ---------- context ----------

def _number_tokens(text: str) -> list[str]:
    return _NUMBER.findall(text.translate(_DEVANAGARI_DIGITS))


def _value(token: str) -> float:
    return float(token.replace(",", "."))


def _state_numbers(state: MatchState, m: Moment) -> list[float]:
    teams = [n for t in (state.home, state.away) for n in (t.goals, t.xg, t.possession_pct, t.shots,
                                                           t.shots_on_target, t.xg_last_5min, t.shots_last_5min)]
    minute = m.t_ms // 60000 + (45 if m.period == 2 else 0)
    player = state.players.get(m.player or "")
    stats = [player.goals, player.shots, player.xg, player.passes, player.top_speed_kmh] if player else []
    # Match intelligence (speeds, distances, pass ratings) is ground truth too, so a variant may quote it.
    accuracy = [a for a in team_pass_accuracy(state).values() if a is not None]  # also in the agents' intel input
    return [*teams, minute, minute + 1, *stats, *intel_numbers(intel_for(m)), *accuracy]


def _players(meta: MatchMeta | None) -> list[tuple[str, str]]:
    return [(p.name, p.name.split()[-1]) for t in ((meta.home, meta.away) if meta else ()) for p in t.players]


def _mentions(text: str, name: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text) is not None


def build_context(p: OverlayProposal, m: Moment | None, meta: MatchMeta | None) -> CheckContext:
    allowed = [_value(t) for t in _number_tokens(p.line)] + (_state_numbers(m.state, m) if m else [])
    players = _players(meta)
    surname_counts = {s: sum(1 for _, other in players if other == s) for _, s in players}
    named = [(full, s) for full, s in players
             if _mentions(p.line, full) or (surname_counts[s] == 1 and _mentions(p.line, s))]
    others = [n for full, s in players if (full, s) not in named
              for n in ((full, s) if surname_counts[s] == 1 else (full,))]
    cited = frozenset(m.event_ids) | {e.event_id for e in p.evidence} if m else frozenset()
    return CheckContext(base_line=p.line, allowed_numbers=tuple(float(a) for a in allowed),
                        required_players=tuple(named), other_players=tuple(others), cited=frozenset(cited),
                        max_chars=LAYER_MAX_CHARS.get(p.layer, 90))


# ---------- checks ----------

def _invents_numbers(v: NarrativeVariant, ctx: CheckContext) -> bool:
    def allowed(token: str) -> bool:
        decimals = len(re.split(r"[.,]", token)[1]) if re.search(r"[.,]", token) else 0
        return any(abs(round(a, decimals) - _value(token)) < 1e-9 for a in ctx.allowed_numbers)
    return not all(allowed(t) for t in _number_tokens(v.text))


def _breaks_names(v: NarrativeVariant, ctx: CheckContext) -> bool:
    dropped = any(not (_mentions(v.text, full) or _mentions(v.text, s)) for full, s in ctx.required_players)
    return dropped or any(_mentions(v.text, name) for name in ctx.other_players)


def _cites_outside_moment(v: NarrativeVariant, ctx: CheckContext) -> bool:
    return bool(ctx.cited) and not set(v.cites) <= ctx.cited


def _untranslated(v: NarrativeVariant, ctx: CheckContext) -> bool:
    if v.lang == BASE_LANG:
        return False
    if v.text.strip().startswith(ctx.base_line.strip()):
        return True
    letters = _LETTER.findall(v.text)
    return v.lang == "hi" and len(_DEVANAGARI.findall(v.text)) < DEVANAGARI_MIN_SHARE * max(1, len(letters))


def check_variant(v: NarrativeVariant, ctx: CheckContext) -> list[str]:
    """Failure codes, in a fixed order; an empty list means the variant may air."""
    failed = {"numbers": _invents_numbers(v, ctx),
              "names": _breaks_names(v, ctx),
              "cites": _cites_outside_moment(v, ctx),
              "length": len(v.text) > ctx.max_chars,
              "banned_topic": any(p.search(v.text) for p in _BANNED),
              "faithfulness": v.faithfulness is not None and v.faithfulness < FAITHFULNESS_MIN,
              "untranslated": _untranslated(v, ctx)}
    return [code for code, is_failed in failed.items() if is_failed]

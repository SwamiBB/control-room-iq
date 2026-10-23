"""Match intelligence for the agents: player speed and distance with threshold indicators, pass quality
(distance, accuracy, difficulty) and ball and shot speed (hackathon expectation ii).

The numbers are ground truth from the stats engine, which fills `Moment.metrics` and `MatchState.last_pass` /
`MatchState.thresholds`. This module only reads them, turns them into plain facts the prompts and fallbacks
can quote, and builds the `intel` block the renderer and console draw. Models never compute these numbers.

Until the stats engine fills `Moment.metrics`, `intel_for` derives what it can from the state snapshot
(the player's running totals, the shot ledger, the last rated pass) so the path works end to end today.
Pure functions: no I/O, no model calls.
"""

from __future__ import annotations

from collections.abc import Callable

from crq_schemas import (
    DifficultyLabel,
    MatchState,
    Moment,
    MomentKind,
    MomentMetrics,
    PassQuality,
    ThresholdIndicator,
)

# Mirror of the stats engine's labels, used only when a pass arrives without one. Keep in step with ingest.
_DIFFICULTY_BANDS: tuple[tuple[float, DifficultyLabel], ...] = ((0.8, "very_hard"), (0.6, "hard"), (0.35, "testing"))

DIFFICULTY_WORDS: dict[str, dict[DifficultyLabel, str]] = {
    "en": {"routine": "routine", "testing": "testing", "hard": "hard", "very_hard": "very hard"},
    "es": {"routine": "sencillo", "testing": "exigente", "hard": "difícil", "very_hard": "muy difícil"},
    "hi": {"routine": "आसान", "testing": "चुनौतीपूर्ण", "hard": "कठिन", "very_hard": "बहुत कठिन"},
}

NameOf = Callable[[str | None], str]
MIN_DISTANCE_M = 1000  # below this a running total is not worth quoting


def difficulty_label(difficulty: float) -> DifficultyLabel:
    return next((label for floor, label in _DIFFICULTY_BANDS if difficulty >= floor), "routine")


def _num(v: float) -> str:
    """One decimal, but whole numbers stay whole (32 km/h, not 32.0)."""
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}"


# ---------- reading the stats engine's output ----------

def _shot_speed(m: Moment) -> float | None:
    rec = next((r for r in m.state.shots if r.event_id in m.event_ids), None)
    return rec.speed_kmh if rec else None


def _key_pass(m: Moment) -> PassQuality | None:
    lp = m.state.last_pass
    if lp is None:
        return None
    if lp.event_id in m.event_ids or (m.player and lp.receiver == m.player and lp.completed):
        return lp
    return None


def _thresholds(m: Moment) -> list[ThresholdIndicator]:
    return [t for t in m.state.thresholds
            if (t.event_id and t.event_id in m.event_ids) or (t.player == m.player and t.play_ms == m.play_ms)]


def _derived_speed_threshold(m: Moment, top_kmh: float) -> list[ThresholdIndicator]:
    """The stats engine raised a speed_threshold moment but sent no indicator: rebuild it from its own rule."""
    from ingest.stats import SPEED_THRESHOLD_KMH  # the engine's rule, not a second copy of it

    return [ThresholdIndicator(kind="top_speed", player=m.player, team=m.team, event_id=m.event_ids[0],
                               play_ms=m.play_ms, value=top_kmh, threshold=SPEED_THRESHOLD_KMH, unit="km/h")]


def intel_for(m: Moment) -> MomentMetrics | None:
    """The moment's expectation (ii) numbers: the stats engine's `metrics` if present, else derived from state.

    The derived path is deliberately narrow: running totals (speed, distance, sprints) only on a speed moment,
    and distance only once it reaches a kilometre, so a card or a foul does not carry noise.
    """
    if m.metrics is not None:
        return m.metrics
    ps = m.state.players.get(m.player or "")
    run = ps if ps is not None and m.kind == MomentKind.SPEED_THRESHOLD else None
    thresholds = _thresholds(m)
    if run is not None and not thresholds and run.top_speed_kmh:
        thresholds = _derived_speed_threshold(m, run.top_speed_kmh)
    derived = MomentMetrics(
        player=m.player,
        player_speed_kmh=run.top_speed_kmh or None if run else None,
        player_top_speed_kmh=run.top_speed_kmh or None if run else None,
        player_distance_km=round(run.distance_m / 1000, 2) if run and run.distance_m >= MIN_DISTANCE_M else None,
        player_sprints=run.sprints or None if run else None,
        key_pass=_key_pass(m),
        shot_speed_kmh=_shot_speed(m),
        thresholds=thresholds,
    )
    has_any = any(v not in (None, []) for k, v in derived.model_dump().items() if k != "player")
    return derived if has_any else None


# ---------- facts for prompts, fallbacks and checks ----------

def threshold_label(t: ThresholdIndicator) -> str:
    if t.label:
        return t.label
    unit = "" if t.unit == "rating" else f" {t.unit}"
    return f"{_num(t.value)}{unit} (threshold {_num(t.threshold)}{unit})"


def pass_fact(p: PassQuality, lang: str = "en") -> str:
    words = DIFFICULTY_WORDS.get(lang, DIFFICULTY_WORDS["en"])
    label = p.difficulty_label if p.difficulty_label != "routine" else difficulty_label(p.difficulty)
    parts = [f"{_num(p.distance_m)} m", f"difficulty {p.difficulty:.2f} ({words[label]})"]
    if p.accuracy_pct is not None:
        parts.append(f"passer accuracy {_num(p.accuracy_pct)}%")
    if p.ball_speed_kmh is not None:
        parts.append(f"ball speed {_num(p.ball_speed_kmh)} km/h")
    return "pass " + ", ".join(parts)


def intel_facts(metrics: MomentMetrics | None, name_of: NameOf = lambda pid: pid or "") -> list[str]:
    """Plain English facts, most important first. Every number here is from the stats engine."""
    if metrics is None:
        return []
    who = name_of(metrics.player) if metrics.player else ""
    facts = []
    for t in metrics.thresholds:
        subject = name_of(t.player) if t.player else "ball"
        facts.append(f"{subject}: {t.kind.replace('_', ' ')} {threshold_label(t)}")
    quoted = {t.value for t in metrics.thresholds}  # do not repeat a speed the threshold line already gives
    if metrics.player_speed_kmh is not None and metrics.player_speed_kmh not in quoted:
        facts.append(f"{who} running at {_num(metrics.player_speed_kmh)} km/h")
    if metrics.key_pass is not None:
        kp = metrics.key_pass
        to = f" to {name_of(kp.receiver)}" if kp.receiver else ""
        facts.append(f"{name_of(kp.player)} {pass_fact(kp)}{to}")
    if metrics.shot_speed_kmh is not None:
        facts.append(f"shot speed {_num(metrics.shot_speed_kmh)} km/h")
    if metrics.ball_speed_kmh is not None:
        facts.append(f"ball speed {_num(metrics.ball_speed_kmh)} km/h")
    if metrics.player_top_speed_kmh is not None and metrics.player_top_speed_kmh not in quoted | {
            metrics.player_speed_kmh}:
        facts.append(f"{who} top speed so far {_num(metrics.player_top_speed_kmh)} km/h")
    if metrics.player_distance_km is not None:
        sprints = f", {metrics.player_sprints} sprints" if metrics.player_sprints else ""
        facts.append(f"{who} distance covered {_num(metrics.player_distance_km)} km{sprints}")
    return facts


def intel_short(metrics: MomentMetrics | None, prefer: str | None = None) -> str | None:
    """One short clause for a lower third or the analyst variant, e.g. 'shot 104.2 km/h'.

    `prefer="pass"` puts the key pass first (a standout-pass moment); otherwise a crossed threshold leads.
    """
    if metrics is None:
        return None
    kp = metrics.key_pass
    pass_clause = f"pass {_num(kp.distance_m)} m, difficulty {kp.difficulty:.2f}" if kp else None
    if prefer == "pass" and pass_clause:
        return pass_clause
    if metrics.thresholds:
        t = metrics.thresholds[0]
        unit = "" if t.unit == "rating" else f" {t.unit}"
        return f"{t.kind.replace('_', ' ')} {_num(t.value)}{unit}"
    if pass_clause:
        return pass_clause
    if metrics.shot_speed_kmh is not None:
        return f"shot {_num(metrics.shot_speed_kmh)} km/h"
    if metrics.player_speed_kmh is not None:
        return f"{_num(metrics.player_speed_kmh)} km/h"
    return None


def intel_numbers(metrics: MomentMetrics | None) -> list[float]:
    """Every number a variant may quote from the moment's intel (the variant checks' allow-list)."""
    if metrics is None:
        return []
    out: list[float] = []
    for v in (metrics.player_speed_kmh, metrics.player_top_speed_kmh, metrics.player_distance_km,
              metrics.player_sprints, metrics.shot_speed_kmh, metrics.ball_speed_kmh):
        if v is not None:
            out.append(float(v))
    if metrics.player_distance_km is not None:
        out.append(round(metrics.player_distance_km * 1000))
    kp = metrics.key_pass
    if kp is not None:
        out += [kp.distance_m, kp.difficulty, round(kp.difficulty * 10), round(kp.difficulty * 100)]
        out += [v for v in (kp.accuracy_pct, kp.ball_speed_kmh) if v is not None]
    for t in metrics.thresholds:
        out += [t.value, t.threshold]
    return out


def _player_ids(metrics: MomentMetrics) -> list[str]:
    kp = metrics.key_pass
    ids = [metrics.player, *(t.player for t in metrics.thresholds), *((kp.player, kp.receiver) if kp else ())]
    return list(dict.fromkeys(i for i in ids if i))


def intel_payload(metrics: MomentMetrics | None, prefer: str | None = None,
                  name_of: NameOf | None = None) -> dict | None:
    """The `intel` block on a proposal's payload: what the renderer and console draw, set by code.

    `names` maps the player ids in the block to display names, so a viewer needs no squad list to draw it.
    """
    if metrics is None:
        return None
    data = metrics.model_dump(mode="json", exclude_none=True)
    if metrics.key_pass is not None and metrics.key_pass.difficulty_label == "routine":
        data["key_pass"]["difficulty_label"] = difficulty_label(metrics.key_pass.difficulty)
    data["short"] = intel_short(metrics, prefer)
    if name_of is not None:
        data["names"] = {pid: name_of(pid) for pid in _player_ids(metrics)}
    return data


def intel_context(m: Moment, name_of: NameOf) -> dict:
    """What the agents receive alongside the moment: the numbers and the facts they may quote."""
    metrics = intel_for(m)
    return {"metrics": metrics.model_dump(mode="json", exclude_none=True) if metrics else None,
            "facts": intel_facts(metrics, name_of),
            "team_pass_accuracy_pct": _team_accuracy(m.state)}


def _team_accuracy(state: MatchState) -> dict[str, float | None]:
    def acc(t) -> float | None:
        if t.pass_accuracy_pct is not None:
            return t.pass_accuracy_pct
        return round(100 * t.passes_completed / t.passes, 1) if t.passes else None
    return {state.home.team: acc(state.home), state.away.team: acc(state.away)}

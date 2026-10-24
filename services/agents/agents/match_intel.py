"""Match intelligence for the agents: player speed and distance with threshold indicators, pass quality
(distance, accuracy, difficulty) and ball and shot speed (hackathon expectation ii).

The numbers are ground truth from the stats engine, which fills `Moment.metrics` and `MatchState.last_pass` /
`MatchState.thresholds`. This module only reads them, turns them into plain facts the prompts and fallbacks
can quote, and builds the `intel` block the renderer and console draw. Models never compute these numbers.

The readers (`intel_for`, `intel_numbers`, `team_pass_accuracy`) live with the stats engine in `ingest.intel`
and are re-exported here. The stats engine now fills `Moment.metrics`; `intel_for` still derives what it can from
the state snapshot for files folded without it. Pure functions: no I/O, no model calls.
"""

from __future__ import annotations

from collections.abc import Callable

from crq_schemas import (
    DifficultyLabel,
    Moment,
    MomentMetrics,
    PassQuality,
    ThresholdIndicator,
)

# The readers and the difficulty bands live with the stats engine (handoff item 7); re-exported here so existing
# imports keep working, and the bands are never kept in two places.
from ingest.derive import difficulty_label as _engine_label
from ingest.intel import MIN_DISTANCE_M, intel_for, intel_numbers, team_pass_accuracy  # noqa: F401

DIFFICULTY_WORDS: dict[str, dict[DifficultyLabel, str]] = {
    "en": {"routine": "routine", "testing": "testing", "hard": "hard", "very_hard": "very hard"},
    "es": {"routine": "sencillo", "testing": "exigente", "hard": "difícil", "very_hard": "muy difícil"},
    "hi": {"routine": "आसान", "testing": "चुनौतीपूर्ण", "hard": "कठिन", "very_hard": "बहुत कठिन"},
}

NameOf = Callable[[str | None], str]


def difficulty_label(difficulty: float) -> DifficultyLabel:
    """The stats engine's label, for a pass that arrives without one."""
    return _engine_label(difficulty)  # type: ignore[return-value]


def _num(v: float) -> str:
    """One decimal, but whole numbers stay whole (32 km/h, not 32.0)."""
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}"


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
            "team_pass_accuracy_pct": team_pass_accuracy(m.state)}

"""Readers of the stats engine's match intelligence: which numbers belong to a moment, and which may be quoted.

They live with the stats engine because they decide what counts as ground truth. The agents use them to build
their `intel` input, and the API's variant checks use them as the allow-list, so neither has to import the other
(docs/HANDOFF-2026-10-24-match-intelligence.md, item 7). Moved here unchanged from agents/match_intel.py, which
re-exports them. Pure functions: no I/O, no model calls.
"""

from __future__ import annotations

from crq_schemas import MatchState, Moment, MomentKind, MomentMetrics, PassQuality, ThresholdIndicator

from .derive import TOP_SPEED_KMH

MIN_DISTANCE_M = 1000  # below this a running total is not worth quoting


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
    return [ThresholdIndicator(kind="top_speed", player=m.player, team=m.team, event_id=m.event_ids[0],
                               play_ms=m.play_ms, value=top_kmh, threshold=TOP_SPEED_KMH, unit="km/h")]


def intel_for(m: Moment) -> MomentMetrics | None:
    """The moment's expectation (ii) numbers: the stats engine's `metrics` if present, else derived from state.

    The derived path (for files folded before metrics existed) is deliberately narrow: running totals only on a
    speed moment, and distance only once it reaches a kilometre, so a card or a foul does not carry noise.
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
        out += [kp.distance_m, kp.difficulty, round(kp.difficulty * 100)]
        out += [v for v in (kp.accuracy_pct, kp.ball_speed_kmh) if v is not None]
    for t in metrics.thresholds:
        out += [t.value, t.threshold]
    return out


def team_pass_accuracy(state: MatchState) -> dict[str, float | None]:
    """Completion % per team, as given to the agents (and so on the variant checks' allow-list)."""
    def acc(t) -> float | None:
        if t.pass_accuracy_pct is not None:
            return t.pass_accuracy_pct
        return round(100 * t.passes_completed / t.passes, 1) if t.passes else None
    return {state.home.team: acc(state.home), state.away.team: acc(state.away)}

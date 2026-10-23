"""Pure helpers for derived state: zone namer, chance quality in plain language, momentum label, hold
advice and the priority table. No I/O; every rule here is written down so the evaluation can check it
(docs/SCHEMA_CHANGES.md sections 3-5).
"""

from __future__ import annotations

from crq_schemas import HoldAdvice, MatchState, MomentKind

WINDOW_MS = 5 * 60 * 1000  # trailing window for xG, shots and pressure
BIG_CHANCE_XG = 0.25  # result beat becomes a big-chance moment (and a proposal) at or above this

# Hold advice: "a goal may follow". Either sustained threat (xG and rising pressure) or a burst of shots.
HOLD_XG_5M = 0.6
HOLD_SHOTS_5M = 3
HOLD_HORIZON_S = 20  # same as the SLA auto-hold

PRIORITY = {
    MomentKind.GOAL: 100,
    MomentKind.RED_CARD: 90,
    MomentKind.BIG_CHANCE: 70,  # result beat; the strike beat is a SHOT moment with priority 0
    MomentKind.CARD: 60,  # stoppage with a card, same stoppage_id as the STOPPAGE moment it supersedes
    MomentKind.HALF_END: 50,
    MomentKind.MATCH_END: 50,
    MomentKind.STOPPAGE: 40,
    MomentKind.MOMENTUM_SHIFT: 30,
    MomentKind.PRESSURE_SPIKE: 30,
    MomentKind.MILESTONE: 10,
    MomentKind.SPEED_THRESHOLD: 10,
    MomentKind.SHOT: 0,  # strike cue only, straight to the viewer
}


def stoppage_importance(snapshot: dict) -> float:
    """Every stoppage reaches the deaf fan (importance >= 0.3, the API's agent threshold); only a penalty or a
    free kick in the final third is worth an operator proposal (>= 0.35, the Producer's fallback threshold)."""
    restart = snapshot.get("restart") or {}
    zone_name = restart.get("zone") or ""
    if restart.get("type") == "penalty" or (restart.get("type") == "free_kick" and zone_name.startswith(
            ("final third", "edge of the box", "inside the box", "six-yard box"))):
        return 0.4
    return 0.32


def zone(x: float | None, y: float | None) -> str | None:
    """Plain-language pitch zone in the acting team's attacking frame (y > 50 is the team's left)."""
    if x is None or y is None:
        return None
    side = "left" if y > 63 else "right" if y < 37 else "centre"
    if x >= 94.5 and 36.8 <= y <= 63.2:
        area = "six-yard box"
    elif x >= 83 and 21.1 <= y <= 78.9:
        area = "inside the box"
    elif x >= 78 and 21.1 <= y <= 78.9:
        area = "edge of the box"
    elif x >= 66.7:
        area = "final third"
    elif x >= 33.3:
        area = "middle third"
    else:
        area = "own third"
    return f"{area}, {side}"


def chance_quality(xg: float) -> str:
    """Fan wording for xG, e.g. 0.38 -> "about 1 in 3 chances like this go in"."""
    if xg >= 0.5:
        return f"about {round(xg * 10)} in 10 chances like this go in"
    n = max(2, round(1 / max(xg, 0.01)))
    return f"about 1 in {n} chances like this go in"


def momentum_label(momentum: list[float]) -> str:
    if not momentum:
        return "even"
    cur, prev = momentum[-1], (momentum[-4] if len(momentum) >= 4 else 0.0)
    if abs(cur - prev) >= 0.6:
        return "swinging"
    if cur > 0.35:
        return "home_on_top"
    if cur < -0.35:
        return "away_on_top"
    return "even"


def hold_advice(state: MatchState, team_id: str, team_name: str) -> HoldAdvice:
    """Computed from state, never by a model. The Producer may word it; it does not decide it."""
    w = state.windows.get(team_id)
    tr = state.pressure_trend.get(team_id)
    xg5, shots5 = (w.xg_5m, w.shots_5m) if w else (0.0, 0)
    slope = tr.slope if tr else 0.0
    if (xg5 >= HOLD_XG_5M and slope > 0) or shots5 >= HOLD_SHOTS_5M:
        return HoldAdvice(recommend="hold", horizon_s=HOLD_HORIZON_S,
                          reason=f"{team_name}: {shots5} shots and {xg5:.2f} xG in the last 5 minutes, "
                                 "pressure rising. A goal may follow.")
    return HoldAdvice(recommend="air", horizon_s=HOLD_HORIZON_S,
                      reason=f"No sustained pressure from {team_name}: {shots5} shot(s) and {xg5:.2f} xG "
                             "in the last 5 minutes.")

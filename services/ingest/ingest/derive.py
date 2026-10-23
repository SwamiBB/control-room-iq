"""Pure rules for derived state, written down so the evaluation can check them. No I/O."""

from __future__ import annotations

WINDOW_MS = 5 * 60 * 1000  # TeamStats.xg_last_5min / shots_last_5min
TREND_MS = 3 * 60 * 1000  # MatchState.pressure_trend looks at the last 3 minutes of play
BIG_CHANCE_XG = 0.25  # a shot at or above this is a big chance: a chance beat on the strike, a result beat after

# pressure_trend: compare the attacking side's threat (xG + 0.01 per pressure in the opponent's half) in the
# last 90 s with the 90 s before. "rising" also needs at least two shots in the 3 minutes, so one isolated
# chance never reads as pressure building (it must not trigger hold advice on its own).
TREND_DELTA = 0.1
TREND_MIN_SHOTS = 2


def zone(x: float | None, y: float | None) -> str:
    """Plain-language pitch zone in the acting team's attacking frame (y > 50 is that team's left)."""
    if x is None or y is None:
        return ""
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
    """Fan wording for xG, e.g. 0.38 -> 'about 1 in 3 chances like this go in' (the newcomer persona's xG)."""
    if xg >= 0.5:
        return f"about {round(xg * 10)} in 10 chances like this go in"
    return f"about 1 in {max(2, round(1 / max(xg, 0.01)))} chances like this go in"


def momentum_label(momentum: list[float]) -> str:
    cur = momentum[-1] if momentum else 0.0
    return "home_pushing" if cur > 0.35 else "away_pushing" if cur < -0.35 else "balanced"


def pressure_trend(late: float, early: float, shots_3min: int) -> str:
    if late - early >= TREND_DELTA and shots_3min >= TREND_MIN_SHOTS:
        return "rising"
    if early - late >= TREND_DELTA:
        return "falling"
    return "steady"


def stoppage_importance(reason: str, restart: str, fouled_x: float | None) -> float:
    """Every foul or offside reaches the deaf fan (>= 0.3, the API's agent threshold); only a penalty or a free
    kick in the final third is worth an operator proposal (>= 0.35, the producer fallback's threshold)."""
    if restart == "penalty" or (restart == "free_kick" and reason == "foul" and (fouled_x or 0) >= 66.7):
        return 0.4
    return 0.32

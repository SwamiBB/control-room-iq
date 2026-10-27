"""Pure rules for derived state, written down so the evaluation can check them. No I/O."""

from __future__ import annotations

import math

WINDOW_MS = 5 * 60 * 1000  # TeamStats.xg_last_5min / shots_last_5min
TREND_MS = 3 * 60 * 1000  # MatchState.pressure_trend looks at the last 3 minutes of play
BIG_CHANCE_XG = 0.25  # a shot at or above this is a big chance: a chance beat on the strike, a result beat after

# pressure_trend: compare the attacking side's threat (xG + 0.01 per pressure in the opponent's half) in the
# last 90 s with the 90 s before. "rising" also needs at least two shots in the 3 minutes, so one isolated
# chance never reads as pressure building (it must not trigger hold advice on its own).
TREND_DELTA = 0.1
TREND_MIN_SHOTS = 2


# Match intelligence (organizers' expectation ii; docs/internal/HANDOFF-2026-10-24-match-intelligence.md). A crossing raises
# a ThresholdIndicator on MatchState.thresholds and on the moment it belongs to.
TOP_SPEED_KMH = 32.0  # a run at or above this is a speed moment
SPRINT_KMH = 25.0  # a carry at or above this counts as a sprint
DISTANCE_KM = (5.0, 10.0)  # running-distance milestones (needs tracking: carry-only distance is far too low)
PASS_DIFFICULTY = 0.8  # a completed pass at or above this is very hard
PASS_DISTANCE_M = 30.0  # a completed pass at or above this is long (the simulator's longest are ~35 m)
SHOT_SPEED_KMH = 100.0
KEEP_PER_KIND = 5  # MatchState.thresholds keeps the latest crossings OF EACH KIND, so ~44 distance marks a match
#                   never push the speed and shot markers out
MIN_DISTANCE_M = 1000  # below this a running total is not worth quoting (an agent would say '0.3 km covered')
HARD_PASS = 0.6  # hard_passes_completed counts completed passes from here (hard and very hard)
# routine < 0.35 <= testing < 0.6 <= hard < 0.8 <= very_hard
DIFFICULTY_BANDS = ((0.8, "very_hard"), (0.6, "hard"), (0.35, "testing"))


def difficulty_label(difficulty: float) -> str:
    return next((label for floor, label in DIFFICULTY_BANDS if difficulty >= floor), "routine")


def _num(v: float) -> str:
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}"


def threshold_label(value: float, threshold: float, unit: str) -> str:
    """Deterministic display text, e.g. '33.1 km/h (over 32)' or '0.86 (over 0.8)' for a rating."""
    if unit == "rating":
        return f"{value:.2f} (over {threshold:g})"
    return f"{_num(value)} {unit} (over {_num(threshold)})"


def distance_to_goal(x: float | None, y: float | None) -> float | None:
    """Metres from (x, y) to the centre of the goal at (100, 50), on a 105 x 68 m pitch."""
    if x is None or y is None:
        return None
    return round(math.hypot((100 - x) * 1.05, (50 - y) * 0.68), 1)


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

"""Deaf-fan strike cue: a visual stand-in for the crowd rising, built by code from the chance beat.

No model call and no generated text, so it may air immediately without passing the operator gate.
"""

from __future__ import annotations

from typing import Literal

from crq_schemas import FanCue, Moment

Pulse = Literal["tap", "pulse", "wave", "surge"]
Direction = Literal["left_to_right", "right_to_left"]

# (minimum importance, pulse) from strongest to weakest; below the last threshold the cue is a tap.
_PULSES: tuple[tuple[float, Pulse], ...] = ((0.9, "surge"), (0.7, "wave"), (0.5, "pulse"))


def _pulse(importance: float) -> Pulse:
    return next((pulse for threshold, pulse in _PULSES if importance >= threshold), "tap")


def _direction(m: Moment, home_team: str) -> Direction | None:
    # Broadcast convention: home attacks left to right in the first half; teams change ends at half time.
    if m.team is None:
        return None
    home_left_to_right = m.period == 1
    attacks_left_to_right = home_left_to_right if m.team == home_team else not home_left_to_right
    return "left_to_right" if attacks_left_to_right else "right_to_left"


def build_fan_cue(m: Moment, home_team: str) -> FanCue:
    # crowd_level uses importance until ingest emits synthetic `crowd` events with a real level.
    return FanCue(cue_id=f"fc-{m.moment_id}", match_id=m.match_id, moment_id=m.moment_id, play_ms=m.play_ms,
                  kind="chance", team=m.team, direction=_direction(m, home_team), crowd_level=m.importance,
                  pulse=_pulse(m.importance))

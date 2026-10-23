"""Play time (what everything is scheduled on) and the period clock (what is displayed)."""

from __future__ import annotations

from dataclasses import dataclass, field

from crq_schemas import MatchEvent


@dataclass
class PlayClock:
    """Tracks the replay position on both time axes.

    v0.2 events carry `play_ms`. Files written before v0.2 carry only `t_ms`, which restarts every
    period, so for those play time is derived by laying the periods end to end.
    """

    period: int = 1
    clock_ms: int = 0
    play_ms: int = 0
    _period_starts: dict[int, int] = field(default_factory=lambda: {1: 0})

    def advance(self, ev: MatchEvent) -> int:
        """Move to the event's time and return the play time elapsed since the previous event."""
        if ev.period != self.period:
            self._period_starts[ev.period] = ev.play_ms - ev.t_ms if ev.play_ms else self.play_ms
            self.period = ev.period
        previous = self.play_ms
        self.clock_ms = ev.t_ms
        self.play_ms = max(previous, ev.play_ms or self._period_starts[self.period] + ev.t_ms)
        return self.play_ms - previous

    def display(self, play_ms: int) -> tuple[int, int]:
        """The (period, clock_ms) a viewer sees at a given play time."""
        period = max(p for p, start in self._period_starts.items() if start <= play_ms or p == 1)
        return period, play_ms - self._period_starts[period]

    def snapshot(self) -> dict[str, int]:
        return {"period": self.period, "clock_ms": self.clock_ms, "play_ms": self.play_ms}

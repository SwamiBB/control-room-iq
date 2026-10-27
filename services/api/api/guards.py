"""Limits for an open demo: the operator console has no sign-in during judging, so these keep a script from
running up the bill or flooding the desk, while staying far above what a person at the console does.

Pure code with an injected clock, so the tests control time. Limits are global, not per client: behind the web
proxy and Container Apps ingress the API can't reliably tell clients apart, and a global cap still bounds the cost.
"""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime

# Defaults sized against real use: an operator fires one graphic every few seconds at most (a goal routine fires
# three at once), types an override in more than three seconds, and a demo window takes minutes to replay.
DECISIONS_PER_MINUTE = 120
OVERRIDES_PER_MINUTE = 20
REPLAY_COOLDOWN_S = 5.0  # stops a tight loop; a person clicking "Run again" never waits
MAX_REPLAY_SPEED = 50.0  # the console's fastest
DEFAULT_AI_MOMENTS_PER_DAY = 300  # about 75 demo-window runs: a safeguard against a runaway script, not a quota


def _daily_moments() -> int:
    """CRQ_DAILY_AI_MOMENTS, read safely: a bad value warns and keeps the default rather than stopping the API.
    The count is kept in memory, so a restart starts the day's count again: fine for a runaway guard."""
    raw = os.environ.get("CRQ_DAILY_AI_MOMENTS", "").strip()
    try:
        value = int(raw) if raw else DEFAULT_AI_MOMENTS_PER_DAY
    except ValueError:
        value = -1
    if value < 0:
        logging.getLogger(__name__).warning("CRQ_DAILY_AI_MOMENTS=%r is not a whole number; using %d", raw,
                                            DEFAULT_AI_MOMENTS_PER_DAY)
        return DEFAULT_AI_MOMENTS_PER_DAY
    return value


AI_MOMENTS_PER_DAY = _daily_moments()


class RateWindow:
    """At most `limit` events in any `window_s` seconds."""

    def __init__(self, limit: int, window_s: float = 60.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit, self.window_s, self.clock = limit, window_s, clock
        self._events: deque[float] = deque()

    def wait(self) -> float | None:
        """The seconds to wait if the window is full, else None. Records nothing."""
        now = self.clock()
        while self._events and now - self._events[0] >= self.window_s:
            self._events.popleft()
        if len(self._events) < self.limit:
            return None
        return self.window_s - (now - self._events[0]) if self._events else self.window_s

    def take(self) -> float | None:
        """Records an event and returns None, or returns the seconds to wait when the window is full."""
        if (left := self.wait()) is not None:
            return left
        self._events.append(self.clock())
        return None


class DailyBudget:
    """How many moments may use the models today (UTC). Past it, moments use the templates: nothing is blocked."""

    def __init__(self, limit: int = AI_MOMENTS_PER_DAY, today: Callable[[], str] | None = None) -> None:
        self.limit = limit
        self.today = today or (lambda: datetime.now(UTC).date().isoformat())
        self._day, self.used = self.today(), 0

    def take(self) -> bool:
        """True, and counts the moment, while today's budget lasts."""
        if (day := self.today()) != self._day:
            self._day, self.used = day, 0
        if self.used >= self.limit:
            return False
        self.used += 1
        return True


def retry_after(seconds: float) -> dict[str, str]:
    return {"Retry-After": str(max(1, round(seconds + 0.5)))}

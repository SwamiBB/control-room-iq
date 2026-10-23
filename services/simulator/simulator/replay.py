"""Replay driver: plays a match file on a clock as a live feed, not a file.

Real event feeds deliver each tagged event 1-3 s after the action, in order, with the strike before its
outcome. The schedule here reproduces that: each event gets a delivery time = action time + feed lag,
where the lag drifts slowly inside [1 s, 3 s] (seeded, so a replay is repeatable) and delivery times never
go backwards, which also guarantees no outcome is delivered before its strike.

ReplayDriver releases the scheduled items on a match clock with play / pause / resume / speed / jump. The
clock and sleep are injectable so tests run instantly. On a jump it calls `on_seek(index)` so the consumer
can fold the skipped events silently before live play resumes.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crq_schemas import EventType, MatchEvent

from .scripted import stream

LAG_MIN_MS, LAG_MAX_MS = 1000, 3000
LAG_STEP_MS = 40  # max drift of the feed lag between consecutive events
TICK_S = 0.05  # how often the driver wakes to react to pause / jump / speed changes


@dataclass
class FeedItem:
    index: int
    action_ms: int  # match time of the action, on one clock across both halves
    delivered_ms: int  # match time the feed delivers it
    event: MatchEvent

    @property
    def latency_ms(self) -> int:
        return self.delivered_ms - self.action_ms

    def envelope(self) -> dict[str, Any]:
        return {"delivered_at": datetime.now(timezone.utc).isoformat(), "delivered_ms": self.delivered_ms,
                "latency_ms": self.latency_ms, "event": self.event.model_dump(mode="json", exclude_none=True)}


def build_schedule(events: list[MatchEvent], seed: int, lag_min_ms: int = LAG_MIN_MS,
                   lag_max_ms: int = LAG_MAX_MS) -> list[FeedItem]:
    rng = stream(seed, "feed_lag")
    p1_end = next((e.t_ms for e in events if e.type == EventType.HALF_END), 0)
    lag = (lag_min_ms + lag_max_ms) / 2
    last = 0
    items = []
    for i, e in enumerate(events):
        action = e.t_ms if e.period == 1 else p1_end + e.t_ms
        lag = min(lag_max_ms, max(lag_min_ms, lag + rng.uniform(-LAG_STEP_MS, LAG_STEP_MS)))
        last = max(last, int(action + lag))
        items.append(FeedItem(index=i, action_ms=action, delivered_ms=last, event=e))
    return items


class ReplayDriver:
    def __init__(self, items: list[FeedItem], speed: float = 1.0, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
                 on_seek: Callable[[int], None] | None = None) -> None:
        self.items = items
        self.speed = speed
        self.clock, self.sleep, self.on_seek = clock, sleep, on_seek
        self.index = 0
        self.position_ms = 0.0
        self._last_wall: float | None = None
        self._playing = asyncio.Event()
        self._playing.set()
        self.done = False

    # ---------- controls ----------
    def _advance(self) -> None:
        now = self.clock()
        if self._last_wall is not None and self._playing.is_set():
            self.position_ms += (now - self._last_wall) * 1000 * self.speed
        self._last_wall = now

    def pause(self) -> None:
        self._advance()
        self._playing.clear()

    def resume(self) -> None:
        self._last_wall = self.clock()
        self._playing.set()

    def set_speed(self, speed: float) -> None:
        if speed <= 0:
            raise ValueError("speed must be positive")
        self._advance()
        self.speed = speed

    def jump(self, period: int, minute: int, second: int = 0) -> int:
        """Seek to the first event at or after period / minute / second (Opta clock). Returns its index."""
        target = (period, minute, second)
        idx = next((it.index for it in self.items
                    if (it.event.period, it.event.minute or 0, it.event.second or 0) >= target), len(self.items))
        self.index = idx
        self.position_ms = float(self.items[idx].delivered_ms) if idx < len(self.items) else self.position_ms
        self._last_wall = self.clock()
        if self.on_seek:
            self.on_seek(idx)
        return idx

    def status(self) -> dict[str, Any]:
        cur = self.items[min(self.index, len(self.items) - 1)].event if self.items else None
        return {"state": "done" if self.done else "playing" if self._playing.is_set() else "paused",
                "index": self.index, "total": len(self.items), "speed": self.speed,
                "position_ms": int(self.position_ms),
                "clock": {"period": cur.period, "minute": cur.minute, "second": cur.second} if cur else None}

    # ---------- loop ----------
    async def run(self, sink: Callable[[FeedItem], Awaitable[None]]) -> None:
        self._last_wall = self.clock()
        while self.index < len(self.items):
            await self._playing.wait()
            self._advance()
            while self.index < len(self.items) and self.items[self.index].delivered_ms <= self.position_ms:
                item = self.items[self.index]
                self.index += 1
                await sink(item)
            if self.index < len(self.items):
                due_s = (self.items[self.index].delivered_ms - self.position_ms) / 1000 / self.speed
                await self.sleep(max(0.0, min(TICK_S, due_s)))
        self.done = True

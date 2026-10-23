"""Replay driver: a feed with 1-3 s lag, strike before outcome, and play / pause / jump / speed controls."""

import asyncio

import pytest
from crq_schemas import EventType
from simulator.replay import ReplayDriver, build_schedule
from simulator.scripted import DATA_DIR, generate, opta_clock


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    async def sleep(self, s: float) -> None:
        self.t += max(s, 0.001)
        await asyncio.sleep(0)


@pytest.fixture(scope="module")
def schedule():
    meta, events = generate(DATA_DIR / "storyline.json")
    return build_schedule(events, meta.seed)


def test_lag_stays_between_one_and_three_seconds(schedule):
    lags = [it.latency_ms for it in schedule]
    assert min(lags) >= 1000 and max(lags) <= 3000
    assert min(lags) < 1500 and max(lags) > 2500, "the lag drifts across the whole range"


def test_delivery_never_goes_backwards_and_strike_precedes_outcome(schedule):
    assert [it.delivered_ms for it in schedule] == sorted(it.delivered_ms for it in schedule)
    for i, it in enumerate(schedule):
        if it.event.type == EventType.SHOT:
            strike = next(s for s in reversed(schedule[:i]) if s.event.type == EventType.SHOT_TAKEN)
            assert strike.event.player == it.event.player and strike.delivered_ms <= it.delivered_ms


def test_same_seed_same_schedule(schedule):
    meta, events = generate(DATA_DIR / "storyline.json")
    assert [it.delivered_ms for it in build_schedule(events, meta.seed)] == [it.delivered_ms for it in schedule]


def _drive(schedule, speed, pause_after=None, on_seek=None):
    clock = FakeClock()
    driver = ReplayDriver(schedule, speed=speed, clock=clock, sleep=clock.sleep, on_seek=on_seek)
    seen = []

    async def sink(item):
        seen.append(item.index)
        if len(seen) == pause_after:
            driver.pause()

    return driver, clock, seen, sink


def test_plays_everything_in_order_at_any_speed(schedule):
    for speed in (50.0, 400.0):
        driver, _, seen, sink = _drive(schedule, speed)
        asyncio.run(driver.run(sink))
        assert seen == list(range(len(schedule))) and driver.done


def test_pause_stops_the_feed_until_resume(schedule):
    async def scenario():
        driver, clock, seen, sink = _drive(schedule, 400.0, pause_after=100)
        task = asyncio.create_task(driver.run(sink))
        while len(seen) < 100:
            await asyncio.sleep(0)
        clock.t += 600  # ten minutes of wall time pass while paused
        for _ in range(20):
            await asyncio.sleep(0)
        assert len(seen) == 100 and driver.status()["state"] == "paused"
        driver.resume()
        await task
        assert seen == list(range(len(schedule)))

    asyncio.run(scenario())


def test_jump_lands_on_the_exact_event_and_tells_the_consumer(schedule):
    seeks = []
    driver, _, seen, sink = _drive(schedule, 400.0, on_seek=seeks.append)
    idx = driver.jump(1, 41, 12)
    first = schedule[idx].event
    assert (first.type, first.player, *opta_clock(first.period, first.t_ms)) == (EventType.SHOT_TAKEN, "har-10", 41, 12)
    assert seeks == [idx]
    asyncio.run(driver.run(sink))
    assert seen[0] == idx and seen == list(range(idx, len(schedule)))

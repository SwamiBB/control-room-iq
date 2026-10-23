from api.clock import PlayClock
from crq_schemas import EventType, MatchEvent


def _ev(seq: int, period: int, t_ms: int, play_ms: int = 0) -> MatchEvent:
    return MatchEvent(event_id=f"e{seq}", match_id="m", seq=seq, period=period, t_ms=t_ms, play_ms=play_ms,
                      type=EventType.PASS)


def test_advance_without_play_ms_stacks_periods_end_to_end():
    clock = PlayClock()
    clock.advance(_ev(1, 1, 0))
    clock.advance(_ev(2, 1, 2_820_000))  # 47:00, first half with stoppage time
    clock.advance(_ev(3, 2, 0))
    assert clock.advance(_ev(4, 2, 60_000)) == 60_000
    assert (clock.period, clock.clock_ms, clock.play_ms) == (2, 60_000, 2_880_000)


def test_advance_prefers_event_play_ms_when_present():
    clock = PlayClock()
    clock.advance(_ev(1, 1, 1_000, play_ms=1_000))
    clock.advance(_ev(2, 2, 5_000, play_ms=2_905_000))
    assert (clock.period, clock.clock_ms, clock.play_ms) == (2, 5_000, 2_905_000)


def test_advance_never_moves_play_time_backwards():
    clock = PlayClock()
    clock.advance(_ev(1, 1, 10_000, play_ms=10_000))
    assert clock.advance(_ev(2, 1, 9_000, play_ms=9_000)) == 0
    assert clock.play_ms == 10_000


def test_display_maps_play_time_back_to_period_clock():
    clock = PlayClock()
    clock.advance(_ev(1, 1, 2_820_000))
    clock.advance(_ev(2, 2, 0))
    assert clock.display(1_000) == (1, 1_000)
    assert clock.display(2_830_000) == (2, 10_000)


def test_snapshot_carries_both_times():
    clock = PlayClock()
    clock.advance(_ev(1, 1, 42_000, play_ms=42_000))
    assert clock.snapshot() == {"period": 1, "clock_ms": 42_000, "play_ms": 42_000}

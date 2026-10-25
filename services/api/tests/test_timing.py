"""Warning before the SLA hold, and the shelf life of a held graphic on both clocks."""

from datetime import UTC, datetime, timedelta

from api.timing import (
    MIN_SHELF_LIFE_MS,
    MIN_SHELF_LIFE_WALL_S,
    is_stale,
    shelf_life_ms,
    sla_times,
    stale_proposals,
)
from api_factories import proposal
from crq_schemas import ProposalStatus

T0 = datetime(2026, 10, 23, 15, 0, tzinfo=UTC)
DESK_MINUTE_PASSED = T0 + timedelta(seconds=MIN_SHELF_LIFE_WALL_S + 1)
PLAY_SHELF_PASSED = 600_000 + MIN_SHELF_LIFE_MS + 1


def _held(pid: str = "p-1", proposed_play_ms: int | None = 600_000, **overrides):
    fields = {"status": ProposalStatus.HELD, "proposed_play_ms": proposed_play_ms, "proposed_at": T0}
    return proposal(pid, **(fields | overrides))


def test_warning_comes_ten_seconds_before_the_hold():
    warn_at, hold_at = sla_times(T0)
    assert (warn_at - T0).total_seconds() == 10 and (hold_at - T0).total_seconds() == 20


def test_warning_never_comes_before_the_proposal():
    warn_at, hold_at = sla_times(T0, hold_s=5, warn_s=10)
    assert warn_at == T0 and (hold_at - T0).total_seconds() == 5


def test_a_held_graphic_expires_once_both_clocks_have_moved_past_its_shelf_life():
    p = _held()
    assert not is_stale(p, 600_000 + MIN_SHELF_LIFE_MS, DESK_MINUTE_PASSED)
    assert is_stale(p, PLAY_SHELF_PASSED, DESK_MINUTE_PASSED)


def test_a_compressed_replay_cannot_expire_a_graphic_the_operator_has_just_been_handed():
    """The speed-20 bug: 20 s of SLA buys 400,000 ms of play, so play time alone expires everything."""
    p = _held()
    just_handed_over = T0 + timedelta(seconds=2)
    assert not is_stale(p, PLAY_SHELF_PASSED, just_handed_over)


def test_a_real_minute_at_the_desk_is_not_enough_on_its_own():
    p = _held()
    assert not is_stale(p, 600_000, T0 + timedelta(hours=1))


def test_play_time_decides_alone_when_the_graphic_never_reached_the_desk():
    assert is_stale(_held(proposed_at=None), PLAY_SHELF_PASSED, T0)


def test_shelf_life_is_the_schedulers_max_delay_when_that_is_longer():
    assert shelf_life_ms(_held(max_delay_ms=120_000)) == 120_000
    assert shelf_life_ms(_held(max_delay_ms=5_000)) == MIN_SHELF_LIFE_MS


def test_only_held_graphics_expire():
    late = 600_000 + 10 * MIN_SHELF_LIFE_MS
    for status in (ProposalStatus.PROPOSED, ProposalStatus.AIRED, ProposalStatus.REJECTED):
        assert not is_stale(_held(status=status), late, DESK_MINUTE_PASSED)


def test_graphics_without_a_play_time_never_expire():
    assert not is_stale(_held(proposed_play_ms=None), 10**9, DESK_MINUTE_PASSED)


def test_a_package_expires_together_in_running_order():
    items = [_held("p-g-2", package_id="pk", package_seq=2), _held("p-g", package_id="pk", package_seq=0),
             _held("p-x", proposed_play_ms=10**9)]
    late = 600_000 + 2 * MIN_SHELF_LIFE_MS
    assert [p.proposal_id for p in stale_proposals(items, late, DESK_MINUTE_PASSED)] == ["p-g", "p-g-2"]

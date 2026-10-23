"""Warning before the SLA hold, and the shelf life of a held graphic."""

from datetime import UTC, datetime

from api.timing import MIN_SHELF_LIFE_MS, is_stale, shelf_life_ms, sla_times, stale_proposals
from api_factories import proposal
from crq_schemas import ProposalStatus

T0 = datetime(2026, 10, 23, 15, 0, tzinfo=UTC)


def _held(pid: str = "p-1", proposed_play_ms: int | None = 600_000, **overrides):
    return proposal(pid, **({"status": ProposalStatus.HELD, "proposed_play_ms": proposed_play_ms} | overrides))


def test_warning_comes_ten_seconds_before_the_hold():
    warn_at, hold_at = sla_times(T0)
    assert (warn_at - T0).total_seconds() == 10 and (hold_at - T0).total_seconds() == 20


def test_warning_never_comes_before_the_proposal():
    warn_at, hold_at = sla_times(T0, hold_s=5, warn_s=10)
    assert warn_at == T0 and (hold_at - T0).total_seconds() == 5


def test_a_held_graphic_expires_once_the_match_moves_past_its_shelf_life():
    p = _held()
    assert not is_stale(p, 600_000 + MIN_SHELF_LIFE_MS)
    assert is_stale(p, 600_000 + MIN_SHELF_LIFE_MS + 1)


def test_shelf_life_is_the_schedulers_max_delay_when_that_is_longer():
    assert shelf_life_ms(_held(max_delay_ms=120_000)) == 120_000
    assert shelf_life_ms(_held(max_delay_ms=5_000)) == MIN_SHELF_LIFE_MS


def test_only_held_graphics_expire():
    late = 600_000 + 10 * MIN_SHELF_LIFE_MS
    for status in (ProposalStatus.PROPOSED, ProposalStatus.AIRED, ProposalStatus.REJECTED):
        assert not is_stale(_held(status=status), late)


def test_graphics_without_a_play_time_never_expire():
    assert not is_stale(_held(proposed_play_ms=None), 10**9)


def test_a_package_expires_together_in_running_order():
    items = [_held("p-g-2", package_id="pk", package_seq=2), _held("p-g", package_id="pk", package_seq=0),
             _held("p-x", proposed_play_ms=10**9)]
    assert [p.proposal_id for p in stale_proposals(items, 600_000 + 2 * MIN_SHELF_LIFE_MS)] == ["p-g", "p-g-2"]

"""Gallery metrics: turnaround, error rate, workload."""

from datetime import UTC, datetime, timedelta

from api.metrics import gallery_metrics
from api_factories import proposal
from crq_schemas import DecisionLogEntry, ProposalStatus

T0 = datetime(2026, 10, 23, 15, 0, tzinfo=UTC)


def _entry(pid: str, action: ProposalStatus, after_s: float, actor: str = "op", package_id: str | None = None):
    return DecisionLogEntry(entry_id=f"d-{pid}-{action.value}", match_id="m", proposal_id=pid, action=action,
                            actor=actor, at=T0 + timedelta(seconds=after_s), package_id=package_id)


def _proposals(*ids: str, **overrides):
    return {pid: proposal(pid, proposed_at=T0, **overrides) for pid in ids}


def test_turnaround_is_measured_from_the_running_order_to_the_fire():
    props = _proposals("p-1", "p-2", "p-3")
    log = [_entry("p-1", ProposalStatus.APPROVED, 2), _entry("p-2", ProposalStatus.APPROVED, 4),
           _entry("p-3", ProposalStatus.OVERRIDDEN, 9)]
    t = gallery_metrics(props, log, [], 600_000, 3).turnaround
    assert (t.fired, t.median_s, t.max_s) == (3, 4.0, 9.0)


def test_holds_and_drops_are_not_counted_as_fired():
    props = _proposals("p-1", "p-2")
    log = [_entry("p-1", ProposalStatus.HELD, 20, actor="sla-timer"), _entry("p-2", ProposalStatus.REJECTED, 3)]
    assert gallery_metrics(props, log, [], 600_000, 0).turnaround.fired == 0


def test_error_rate_counts_overrides_drops_and_check_failures():
    props = _proposals("p-1", "p-2", "p-3", "p-4")
    log = [_entry("p-1", ProposalStatus.APPROVED, 1), _entry("p-2", ProposalStatus.OVERRIDDEN, 1),
           _entry("p-3", ProposalStatus.REJECTED, 1), _entry("p-4", ProposalStatus.APPROVED, 1)]
    deliveries = [{"source": "variant", "failures": []}, {"source": "template", "failures": ["numbers"]},
                  {"source": "base", "failures": ["untranslated", "numbers"]}]
    e = gallery_metrics(props, log, deliveries, 600_000, 3).errors
    assert (e.decided, e.overridden, e.dropped, e.override_rate, e.drop_rate) == (4, 1, 1, 0.25, 0.25)
    assert e.deliveries == {"variant": 1, "template": 1, "base": 1}
    assert e.check_failures == {"numbers": 2, "untranslated": 1}


def test_sla_holds_are_workload_for_the_timer_not_the_operator():
    props = _proposals("p-1", "p-2")
    log = [_entry("p-1", ProposalStatus.HELD, 20, actor="sla-timer"), _entry("p-2", ProposalStatus.APPROVED, 2)]
    w = gallery_metrics(props, log, [], 1_200_000, 1).workload
    assert (w.operator_decisions, w.sla_holds, w.decisions_per_10_min, w.play_minutes) == (1, 1, 0.5, 20.0)


def test_one_click_on_a_package_counts_once_and_fires_three_graphics():
    props = _proposals("p-g", "p-g-1", "p-g-2", package_id="pk-p-g")
    log = [_entry(pid, ProposalStatus.APPROVED, 3, package_id="pk-p-g") for pid in props]
    w = gallery_metrics(props, log, [], 600_000, 3).workload
    assert (w.operator_decisions, w.packages_fired, w.graphics_per_click) == (1, 1, 3.0)


def test_empty_match_has_no_rates():
    m = gallery_metrics({}, [], [], 0, 0)
    assert m.turnaround.median_s is None and m.errors.override_rate is None
    assert m.workload.decisions_per_10_min is None and m.workload.graphics_per_click is None

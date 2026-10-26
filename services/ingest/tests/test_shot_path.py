"""Where a shot finished, for the pitch views: on the shot ledger and as the moment's own two-point path."""

from __future__ import annotations

import pytest
from crq_schemas import MomentKind
from ingest.stats import StateFolder
from simulator.scripted import DATA_DIR, generate


@pytest.fixture(scope="module")
def ref():
    meta, events = generate(DATA_DIR / "storyline.json")
    folder = StateFolder(meta)
    return folder, [m for ev in events for m in folder.apply(ev)], {e.event_id: e for e in events}


def test_shot_records_carry_where_the_shot_finished(ref):
    folder, _, by_id = ref
    shots = folder.state.shots
    assert shots
    for r in shots:
        ev = by_id[r.event_id]
        assert (r.end_x, r.end_y) == (ev.end_x, ev.end_y)
        assert r.end_x is not None and r.end_y is not None


def test_a_shot_moment_carries_its_own_shot_as_a_path(ref):
    _, moments, by_id = ref
    results = [m for m in moments if m.kind in (MomentKind.BIG_CHANCE, MomentKind.GOAL) and m.beat == "result"]
    assert results
    for m in results:
        ev = by_id[m.event_ids[0]]
        assert m.metrics.shot_path == [(ev.x, ev.y), (ev.end_x, ev.end_y)]


def test_the_strike_has_no_path_until_the_shot_has_finished(ref):
    _, moments, _ = ref
    strikes = [m for m in moments if m.beat == "chance"]
    assert strikes
    assert all(m.metrics is None or m.metrics.shot_path is None for m in strikes)


def test_moments_that_are_not_shots_have_no_path(ref):
    _, moments, _ = ref
    others = [m for m in moments if m.kind not in (MomentKind.BIG_CHANCE, MomentKind.GOAL) and m.metrics]
    assert others
    assert all(m.metrics.shot_path is None for m in others)

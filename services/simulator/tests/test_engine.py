from collections import Counter

from crq_schemas import EventType
from simulator.cli import build_meta
from simulator.engine import MatchEngine


def _run(seed: int):
    meta = build_meta(seed)
    return meta, list(MatchEngine(meta).run())


def test_deterministic_for_seed():
    _, a = _run(7)
    _, b = _run(7)
    assert [e.event_id for e in a] == [e.event_id for e in b]
    assert [e.t_ms for e in a] == [e.t_ms for e in b]


def test_football_realistic_volumes():
    _, evs = _run(42)
    c = Counter(e.type for e in evs)
    assert 500 <= c[EventType.PASS] <= 1400, c[EventType.PASS]
    assert 8 <= c[EventType.SHOT] <= 45, c[EventType.SHOT]
    assert c[EventType.PRESSURE] > 50
    assert c[EventType.MATCH_END] == 1 and c[EventType.HALF_END] == 1
    goals = sum(1 for e in evs if e.type == EventType.SHOT and e.outcome == "goal")
    assert goals <= 10


def test_events_are_ordered_and_bounded():
    _, evs = _run(3)
    seqs = [e.seq for e in evs]
    assert seqs == sorted(seqs)
    for e in evs:
        for v in (e.x, e.y, e.end_x, e.end_y):
            if v is not None:
                assert 0 <= v <= 100
        if e.type == EventType.SHOT:
            assert 0 < e.attrs["xg"] < 1

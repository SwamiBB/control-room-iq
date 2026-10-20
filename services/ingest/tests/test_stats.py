from crq_schemas import MomentKind
from ingest.stats import StateFolder
from simulator.cli import build_meta
from simulator.engine import MatchEngine


def test_fold_full_match():
    meta = build_meta(42)
    folder = StateFolder(meta)
    moments = [m for ev in MatchEngine(meta).run() for m in folder.apply(ev)]
    s = folder.state
    assert abs(s.home.possession_pct + s.away.possession_pct - 100) < 0.2
    assert s.home.passes_completed <= s.home.passes
    assert s.home.goals == sum(p.goals for p in s.players.values() if p.team == s.home.team)
    kinds = {m.kind for m in moments}
    assert MomentKind.MATCH_END in kinds and MomentKind.HALF_END in kinds
    assert any(m.kind in (MomentKind.GOAL, MomentKind.BIG_CHANCE) for m in moments)
    assert all(m.event_ids for m in moments)
    assert len(s.momentum) >= 85

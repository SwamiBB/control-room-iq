import os

os.environ["CRQ_OFFLINE"] = "1"

import asyncio  # noqa: E402
from typing import get_args  # noqa: E402

import pytest  # noqa: E402
from agents.workflow import MomentPipeline, priority_from_importance  # noqa: E402
from crq_schemas import Access, MomentKind, Persona  # noqa: E402
from ingest.stats import StateFolder  # noqa: E402
from simulator.cli import build_meta  # noqa: E402
from simulator.engine import MatchEngine  # noqa: E402


def _first_goal():
    meta = build_meta(42)
    folder = StateFolder(meta)
    return next(m for ev in MatchEngine(meta).run() for m in folder.apply(ev) if m.kind == MomentKind.GOAL)


def test_offline_pipeline_produces_proposal_for_goal():
    goal = _first_goal()
    res = asyncio.run(MomentPipeline().process(goal))
    assert res.failures == []
    assert res.proposal is not None and res.proposal.layer.value == "full_screen"
    assert res.explanation.cites == goal.event_ids


def test_offline_variants_cover_every_persona_access_and_language():
    res = asyncio.run(MomentPipeline().process(_first_goal()))
    combos = {(v.persona, v.access, v.lang) for v in res.variants}
    assert combos == {(p, a, lang) for p in Persona for a in get_args(Access) for lang in ("en", "es", "hi")}


def test_offline_deaf_access_states_the_score_for_every_persona():
    goal = _first_goal()
    res = asyncio.run(MomentPipeline().process(goal))
    score = f"The score is {goal.state.home.goals} to {goal.state.away.goals}."
    deaf = [v for v in res.variants if v.access == "deaf"]
    assert {v.persona for v in deaf} == set(Persona)
    assert all(v.text.endswith(score) for v in deaf)


def test_offline_pipeline_produces_valid_proposal_for_non_goal_moments():
    # Goals have importance 1.0, which hid the float -> int priority break; cover fractional importance too.
    meta = build_meta(42)
    folder = StateFolder(meta)
    moments = [m for ev in MatchEngine(meta).run() for m in folder.apply(ev) if 0.35 <= m.importance < 1.0]
    assert moments
    pipeline = MomentPipeline()
    for m in moments[:10]:
        res = asyncio.run(pipeline.process(m))
        assert res.failures == []
        assert res.proposal is not None and isinstance(res.proposal.priority, int) and res.proposal.priority >= 2


@pytest.mark.parametrize(("importance", "expected"), [(1.0, 1), (0.5, 5), (0.35, 6), (0.0, 9)])
def test_priority_from_importance_maps_unit_score_to_rank(importance, expected):
    assert priority_from_importance(importance) == expected

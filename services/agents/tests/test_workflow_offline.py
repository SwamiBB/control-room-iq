import os

os.environ["CRQ_OFFLINE"] = "1"

import asyncio  # noqa: E402

from agents.workflow import MomentPipeline  # noqa: E402
from crq_schemas import MomentKind, Persona  # noqa: E402
from ingest.stats import StateFolder  # noqa: E402
from simulator.cli import build_meta  # noqa: E402
from simulator.engine import MatchEngine  # noqa: E402


def test_offline_pipeline_produces_proposal_for_goal():
    meta = build_meta(42)
    folder = StateFolder(meta)
    goal = next(m for ev in MatchEngine(meta).run() for m in folder.apply(ev) if m.kind == MomentKind.GOAL)
    res = asyncio.run(MomentPipeline().process(goal))
    assert res.failures == []
    assert res.proposal is not None and res.proposal.layer.value == "full_screen"
    assert res.explanation.cites == goal.event_ids
    assert {v.persona for v in res.variants} == set(Persona)
    assert {v.lang for v in res.variants} == {"en", "es", "hi", "ar"}

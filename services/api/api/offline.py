"""Headless offline run: a reference match through the whole pipeline with no Azure and no clock.

  CRQ_OFFLINE=1 python -m api.offline                              # reference match, check the demo moments
  CRQ_OFFLINE=1 python -m api.offline data/reference_match_m2.jsonl --storyline data/storyline_m2.json

Same path as POST /matches/replay (StateFolder -> MomentPipeline), minus the sleeps and websockets, so it
runs in seconds in CI. The check compares the moments that came out with the storyline's demo beats:
each must appear at its scripted minute, and proposal-worthy ones must produce a proposal.
"""

from __future__ import annotations

import os

os.environ.setdefault("CRQ_OFFLINE", "1")  # before agents.config reads it

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

import time  # noqa: E402

from agents.workflow import MomentPipeline  # noqa: E402
from crq_schemas import EvaluationRecord, MatchEvent, MatchMeta, Moment, MomentKind, OverlayProposal  # noqa: E402
from ingest.stats import StateFolder  # noqa: E402

from api import evaluation  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DEFAULT_MATCH = REPO / "data" / "reference_match.jsonl"
DEFAULT_STORY = REPO / "data" / "storyline.json"

# storyline beat kind -> the moment that must appear for it (and whether it must reach a proposal)
EXPECTED = {
    "shot": (MomentKind.BIG_CHANCE, True),
    "goal": (MomentKind.GOAL, True),
    "chance_then_rebound_goal": (MomentKind.GOAL, True),
    "penalty_goal": (MomentKind.GOAL, True),
    "foul": (MomentKind.STOPPAGE, False),
    "red_card": (MomentKind.RED_CARD, True),
    "offside": (MomentKind.STOPPAGE, False),
    "half_end": (MomentKind.HALF_END, True),
    "match_end": (MomentKind.MATCH_END, True),
}


@dataclass
class Row:
    moment: Moment
    proposal_layer: str | None
    failures: list[str]
    proposal: OverlayProposal | None = None

    def line(self) -> str:
        m = self.moment
        hold = m.snapshot.get("hold_advice", {}).get("recommend")
        return (f"[{m.period}H {m.state.minute:>3}'] {m.kind.value:15s} p{m.priority:<3} {m.beat:6s} "
                f"{(self.proposal_layer or '-'):12s} {('hold advice: ' + hold) if hold else ''}  {m.summary}")


async def replay_offline(match_path: Path = DEFAULT_MATCH, min_importance: float = 0.3,
                         records: list[EvaluationRecord] | None = None) -> list[Row]:
    """`records`, if given, collects one EvaluationRecord per agent output (same rows as the live API)."""
    pipeline = MomentPipeline()
    rows: list[Row] = []
    with match_path.open(encoding="utf-8") as f:
        folder = StateFolder(MatchMeta.model_validate_json(f.readline()))
        for line in f:
            if not line.strip():
                continue
            for m in folder.apply(MatchEvent.model_validate_json(line)):
                if m.importance < min_importance:
                    rows.append(Row(m, None, []))  # strike beats etc.: recorded, not sent to the agents
                    continue
                t0 = time.monotonic()
                res = await pipeline.process(m)
                if records is not None:
                    records += evaluation.records_for(m, res, int((time.monotonic() - t0) * 1000),
                                                      os.environ.get("CRQ_OFFLINE") == "1")
                rows.append(Row(m, res.proposal.layer.value if res.proposal else None, res.failures, res.proposal))
    return rows


def check_demo_moments(story: dict[str, Any], rows: list[Row]) -> list[str]:
    """Return one problem per storyline beat that did not come out as expected (empty list = pass)."""
    problems = []
    for b in story["beats"]:
        shots = b["shots"] if b["kind"] == "pressure_build" else [b]
        for s in shots:
            kind = "shot" if b["kind"] == "pressure_build" else b["kind"]
            want, needs_proposal = EXPECTED[kind]
            minute = s.get("minute", b.get("minute"))
            if kind == "shot" and s["xg"] < 0.25:
                want, needs_proposal = MomentKind.SHOT, False  # below the big-chance gate: strike cue only
            hits = [r for r in rows if r.moment.kind == want and r.moment.period == b["period"]
                    and r.moment.state.minute in (minute, minute + 1)]
            if not hits:
                problems.append(f"{b['id']}: no {want.value} moment at {minute}'")
            elif needs_proposal and not any(r.proposal_layer for r in hits):
                problems.append(f"{b['id']}: {want.value} at {minute}' produced no proposal")
    return problems


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="api.offline")
    p.add_argument("match", nargs="?", default=str(DEFAULT_MATCH))
    p.add_argument("--storyline", default=str(DEFAULT_STORY))
    p.add_argument("--all", action="store_true", help="print every moment, not only those sent to the agents")
    p.add_argument("--eval-out", help="write the evaluation rows as Foundry JSONL here")
    a = p.parse_args(argv)
    records: list[EvaluationRecord] = []
    rows = asyncio.run(replay_offline(Path(a.match), records=records))
    if a.eval_out:
        Path(a.eval_out).write_text(evaluation.to_foundry_jsonl(records), encoding="utf-8")
        print(f"{len(records)} evaluation rows -> {a.eval_out}", file=sys.stderr)
    for r in rows:
        if a.all or r.proposal_layer or r.moment.importance >= 0.3:
            print(r.line())
    failures = [f for r in rows for f in r.failures]
    problems = check_demo_moments(json.loads(Path(a.storyline).read_text(encoding="utf-8")), rows)
    print(f"\n{len(rows)} moments, {sum(1 for r in rows if r.proposal_layer)} proposals, "
          f"{len(failures)} agent failures", file=sys.stderr)
    for pr in problems:
        print(f"DEMO MOMENT MISSING: {pr}", file=sys.stderr)
    print("demo moments: all present" if not problems else f"demo moments: {len(problems)} missing", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

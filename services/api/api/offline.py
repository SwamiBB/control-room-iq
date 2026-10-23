"""Headless offline run: a reference match through state, moments and the agent pipeline, no Azure, no clock.

  CRQ_OFFLINE=1 python -m api.offline                                  # reference match, seed 42
  CRQ_OFFLINE=1 python -m api.offline data/reference/match-007.jsonl --storyline data/storyline_m2.json

Same path as POST /matches/replay (StateFolder -> MomentPipeline) without the sleeps and websockets, so it runs
in seconds. It then checks the storyline's beats against the moments that came out: each must appear at its
scripted minute, and the proposal-worthy ones must produce a proposal. Read-only on the API: nothing here is
imported by main.py.
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

from agents.workflow import MomentPipeline  # noqa: E402
from crq_schemas import MatchEvent, MatchMeta, Moment, MomentKind, OverlayProposal  # noqa: E402
from ingest.stats import StateFolder  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DEFAULT_MATCH = REPO / "data" / "reference" / "match-042.jsonl"
DEFAULT_STORY = REPO / "data" / "storyline.json"
MIN_IMPORTANCE = 0.3  # as POST /matches/replay

# storyline beat kind -> (moment kind, beat, must it reach a proposal)
EXPECTED: dict[str, tuple[MomentKind, str | None, bool]] = {
    "shot": (MomentKind.BIG_CHANCE, "result", True),
    "goal": (MomentKind.GOAL, "result", True),
    "chance_then_rebound_goal": (MomentKind.GOAL, "result", True),
    "penalty_goal": (MomentKind.GOAL, "result", True),
    "foul": (MomentKind.STOPPAGE, None, False),
    "red_card": (MomentKind.CARD, None, True),
    "offside": (MomentKind.STOPPAGE, None, False),
    "half_end": (MomentKind.HALF_END, None, True),
    "match_end": (MomentKind.MATCH_END, None, True),
}


def _minute(m: Moment) -> int:
    return m.t_ms // 60000 + (45 if m.period == 2 else 0)


@dataclass
class Row:
    moment: Moment
    proposal: OverlayProposal | None
    failures: list[str]

    def line(self) -> str:
        m = self.moment
        layer = self.proposal.layer.value if self.proposal else "-"
        head = f"[{m.period}H {_minute(m):>3}'] {m.kind.value:15s} {m.beat:6s}"
        return f"{head} {m.importance:.2f} {layer:12s} {m.summary}"


async def replay_offline(match_path: Path = DEFAULT_MATCH, min_importance: float = MIN_IMPORTANCE) -> list[Row]:
    pipeline = MomentPipeline()
    rows: list[Row] = []
    with match_path.open(encoding="utf-8") as f:
        folder = StateFolder(MatchMeta.model_validate_json(f.readline()))
        for line in filter(str.strip, f):
            for m in folder.apply(MatchEvent.model_validate_json(line)):
                if m.importance < min_importance:
                    rows.append(Row(m, None, []))  # recorded, never sent to the agents
                    continue
                res = await pipeline.process(m)
                rows.append(Row(m, res.proposal, res.failures))
    return rows


def check_demo_moments(story: dict[str, Any], rows: list[Row]) -> list[str]:
    """One problem per storyline beat that did not come out as expected; an empty list means pass."""
    problems = []
    for b in story["beats"]:
        beats = b["shots"] if b["kind"] == "pressure_build" else [b]
        for s in beats:
            kind = "shot" if b["kind"] == "pressure_build" else b["kind"]
            want, beat, needs_proposal = EXPECTED[kind]
            if kind == "shot" and s["xg"] < 0.25:  # below the big-chance gate: no big-chance moment, by design
                continue
            minute = s.get("minute", b.get("minute"))
            hits = [r for r in rows if r.moment.kind == want and r.moment.period == b["period"]
                    and _minute(r.moment) in (minute, minute + 1) and (beat is None or r.moment.beat == beat)]
            if not hits:
                problems.append(f"{b['id']}: no {want.value} moment at {minute}'")
            elif needs_proposal and not any(r.proposal for r in hits):
                problems.append(f"{b['id']}: {want.value} at {minute}' produced no proposal")
    return problems


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="api.offline")
    p.add_argument("match", nargs="?", default=str(DEFAULT_MATCH))
    p.add_argument("--storyline", default=str(DEFAULT_STORY))
    p.add_argument("--all", action="store_true", help="print every moment, not only those sent to the agents")
    a = p.parse_args(argv)
    rows = asyncio.run(replay_offline(Path(a.match)))
    for r in rows:
        if a.all or r.moment.importance >= MIN_IMPORTANCE:
            print(r.line())
    problems = check_demo_moments(json.loads(Path(a.storyline).read_text(encoding="utf-8")), rows)
    failures = sum(len(r.failures) for r in rows)
    print(f"\n{len(rows)} moments, {sum(1 for r in rows if r.proposal)} proposals, {failures} agent failures",
          file=sys.stderr)
    for pr in problems:
        print(f"DEMO MOMENT MISSING: {pr}", file=sys.stderr)
    print("demo moments: all present" if not problems else f"demo moments: {len(problems)} missing", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

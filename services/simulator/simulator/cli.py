"""Simulator CLI.

  python -m simulator.cli generate --seed 42 --out data/match-001.jsonl
  python -m simulator.cli replay data/match-001.jsonl --speed 20            # to stdout
  python -m simulator.cli replay data/match-001.jsonl --speed 20 --eventhub # to Azure Event Hubs

The first line of a match file is the MatchMeta record; the rest are MatchEvent records.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from crq_schemas import MatchEvent, MatchMeta

from .engine import MatchEngine, new_match_id
from .squads import generate_team, pick_venue


def build_meta(seed: int, home_idx: int = 0, away_idx: int = 1) -> MatchMeta:
    return MatchMeta(match_id=new_match_id() if seed == 0 else f"m-{seed:06d}",
                     venue=pick_venue(seed), kickoff_utc=datetime.now(UTC),
                     home=generate_team(home_idx, seed), away=generate_team(away_idx, seed), seed=seed)


def cmd_generate(args: argparse.Namespace) -> None:
    meta = build_meta(args.seed, args.home, args.away)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8") as f:
        f.write(meta.model_dump_json() + "\n")
        for ev in MatchEngine(meta).run():
            f.write(ev.model_dump_json() + "\n")
            n += 1
    print(f"wrote {n} events for {meta.home.name} v {meta.away.name} -> {out}", file=sys.stderr)


def iter_file(path: Path):
    with path.open(encoding="utf-8") as f:
        meta = MatchMeta.model_validate_json(f.readline())
        for line in f:
            if line.strip():
                yield meta, MatchEvent.model_validate_json(line)


async def _replay(args: argparse.Namespace) -> None:
    producer = None
    if args.eventhub:
        from azure.eventhub.aio import EventHubProducerClient
        from azure.identity.aio import DefaultAzureCredential

        producer = EventHubProducerClient(fully_qualified_namespace=os.environ["EVENTHUB_NAMESPACE"],
                                          eventhub_name=os.environ.get("EVENTHUB_EVENTS", "crq-events"),
                                          credential=DefaultAzureCredential())
    last_t, last_period = 0, 1
    wall = time.monotonic()
    batch = []
    try:
        for meta, ev in iter_file(Path(args.file)):
            if ev.period != last_period:
                last_t, last_period = 0, ev.period
            delay = max(0, (ev.t_ms - last_t) / 1000 / args.speed)
            last_t = ev.t_ms
            if delay > 0:
                await asyncio.sleep(delay)
            if producer:
                from azure.eventhub import EventData
                batch.append(EventData(ev.model_dump_json()))
                if len(batch) >= 20 or ev.type.value in ("shot", "match_end", "half_end"):
                    await producer.send_batch(batch, partition_key=meta.match_id)
                    batch = []
            else:
                print(ev.model_dump_json(), flush=True)
    finally:
        if producer:
            if batch:
                await producer.send_batch(batch)
            await producer.close()
    print(f"replayed in {time.monotonic() - wall:.1f}s", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="simulator")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--home", type=int, default=0)
    g.add_argument("--away", type=int, default=1)
    g.add_argument("--out", default="data/match.jsonl")
    g.set_defaults(fn=cmd_generate)
    r = sub.add_parser("replay")
    r.add_argument("file")
    r.add_argument("--speed", type=float, default=10.0, help="match-clock multiplier")
    r.add_argument("--eventhub", action="store_true")
    r.set_defaults(fn=lambda a: asyncio.run(_replay(a)))
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()

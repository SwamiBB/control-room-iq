"""Simulator CLI.

  python -m simulator.cli generate --seed 42 --out data/match-001.jsonl
  python -m simulator.cli replay data/match-001.jsonl --speed 20            # to stdout
  python -m simulator.cli replay data/match-001.jsonl --speed 20 --eventhub # to Azure Event Hubs
  python -m simulator.cli generate --storyline data/storyline.json --out data/reference/match-042.jsonl
  python -m simulator.cli reference              # all data/storyline*.json -> data/reference/ (+ tracking)
  python -m simulator.cli calibrate --start 1000 --count 200 --out docs/CALIBRATION.md
  python -m simulator.cli view --seed 42              # top-down preview -> data/view-042.html

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

from . import calibrate, scripted, tracking, viewer
from .engine import MatchEngine, new_match_id
from .squads import generate_team, pick_venue


def build_meta(seed: int, home_idx: int = 0, away_idx: int = 1) -> MatchMeta:
    return MatchMeta(match_id=new_match_id() if seed == 0 else f"m-{seed:06d}",
                     venue=pick_venue(seed), kickoff_utc=datetime.now(UTC),
                     home=generate_team(home_idx, seed), away=generate_team(away_idx, seed), seed=seed)


def write_match(out: Path, meta: MatchMeta, events) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write(meta.model_dump_json() + "\n")
        for ev in events:
            f.write(ev.model_dump_json() + "\n")
            n += 1
    return n


def cmd_generate(args: argparse.Namespace) -> None:
    if args.storyline:
        meta, events = scripted.generate(Path(args.storyline))
    else:
        meta = build_meta(args.seed, args.home, args.away)
        events = MatchEngine(meta).run()
    out = Path(args.out)
    n = write_match(out, meta, events)
    print(f"wrote {n} events for {meta.home.name} v {meta.away.name} -> {out}", file=sys.stderr)


REFERENCE_DIR = scripted.DATA_DIR / "reference"


def reference_paths(story: Path) -> tuple[Path, Path]:
    """storyline.json (seed 42) -> data/reference/match-042.jsonl + tracking-042.jsonl.gz."""
    seed = scripted.load_storyline(story)["seed"]
    return REFERENCE_DIR / f"match-{seed:03d}.jsonl", REFERENCE_DIR / f"tracking-{seed:03d}.jsonl.gz"


def cmd_reference(args: argparse.Namespace) -> None:
    stories = [Path(s) for s in args.storyline] or sorted(scripted.DATA_DIR.glob("storyline*.json"))
    for story in stories:
        meta, events = scripted.generate(story)
        match_path, tracking_path = reference_paths(story)
        n = write_match(match_path, meta, events)
        tracking_path.parent.mkdir(parents=True, exist_ok=True)
        end = next(e for e in events if e.type.value == "match_end")
        msg = f"{story.name}: {n} events, final {end.attrs['score']} -> {match_path.name}"
        if not args.no_tracking:
            frames, _ = tracking.build_tracking(meta, events)
            tracking.write_tracking(tracking_path, frames, meta)
            msg += f", {len(frames)} frames -> {tracking_path.name}"
        print(msg, file=sys.stderr)


def cmd_view(args: argparse.Namespace) -> None:
    out = Path(args.out or scripted.DATA_DIR / f"view-{args.seed:03d}.html")
    n = viewer.build_view(args.seed, out)
    print(f"{n} frames -> {out}  (open it in a browser)", file=sys.stderr)


def cmd_calibrate(args: argparse.Namespace) -> None:
    engine_rows = calibrate.calibrate_engine(args.start, args.count)
    meta, events = scripted.generate(scripted.DATA_DIR / "storyline.json")
    _, summary = tracking.build_tracking(meta, events)
    changed = {e.attrs.get("off") for e in events if e.type.value == "substitution"}
    changed |= {e.player for e in events if e.type.value == "card" and e.attrs.get("color") in ("red", "second_yellow")}
    full_match = {p.player_id for t in (meta.home, meta.away) for p in t.players
                  if p.number <= 11 and p.position != "GK" and p.player_id not in changed}
    md = calibrate.to_markdown(engine_rows, args.start, args.count, calibrate.calibrate_tracking(summary, full_match),
                               "the reference match (storyline.json)")
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
    print(md)


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
    g.add_argument("--storyline", help="storyline JSON; scripts the match instead of free play")
    g.set_defaults(fn=cmd_generate)
    ref = sub.add_parser("reference", help="generate the reference matches from data/storyline*.json")
    ref.add_argument("storyline", nargs="*", help="storyline files (default: all data/storyline*.json)")
    ref.add_argument("--no-tracking", action="store_true")
    ref.set_defaults(fn=cmd_reference)
    view = sub.add_parser("view", help="top-down preview of a reference match (one HTML file)")
    view.add_argument("--seed", type=int, default=42, help="42 reference, 7 red card, 101 comeback")
    view.add_argument("--out", help="default: data/view-<seed>.html")
    view.set_defaults(fn=cmd_view)
    cal = sub.add_parser("calibrate", help="realism table over a seed range")
    cal.add_argument("--start", type=int, default=1000)
    cal.add_argument("--count", type=int, default=200)
    cal.add_argument("--out", help="write the markdown table here, e.g. docs/CALIBRATION.md")
    cal.set_defaults(fn=cmd_calibrate)
    r = sub.add_parser("replay")
    r.add_argument("file")
    r.add_argument("--speed", type=float, default=10.0, help="match-clock multiplier")
    r.add_argument("--eventhub", action="store_true")
    r.set_defaults(fn=lambda a: asyncio.run(_replay(a)))
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()

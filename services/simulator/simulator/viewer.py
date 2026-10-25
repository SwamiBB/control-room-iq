"""Developer preview of a reference match: the tracking stream animated on a top-down pitch, in one HTML file.

  python -m simulator.cli view --seed 42          # writes data/view-042.html; open it in a browser

For looking at the simulator's output (players at the ball, the shape, pressing, lofted balls), not the product
console. Players in club colours with shirt numbers, the ball with its height and a short trail, the clock, the
score, a caption per event, play / pause / speed / scrub, and a jump button per storyline demo moment. Reads the
committed files in data/reference/, so it shows exactly what the rest of the pipeline sees.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from .scripted import DATA_DIR, load_storyline

TEMPLATE = Path(__file__).with_name("viewer.html")
JUMP_LEAD_S = 5  # start each jump a few seconds before the moment


def _captions(events: list[dict], names: dict[str, str], home: str, away: str) -> list[list[Any]]:
    out, score = [], {home: 0, away: 0}
    for e in events:
        kind, who, a = e["type"], names.get(e.get("player") or "", ""), e.get("attrs", {})
        text = None
        if kind == "shot_taken":
            text = f"{who} shoots (xG {a.get('xg')})"
        elif kind == "shot":
            if e["outcome"] == "goal":
                score[e["team"]] += 1
                text = f"GOAL! {who}"
            else:
                text = f"{who}: {e['outcome'].replace('_', ' ')}"
        elif kind == "foul":
            text = f"Foul by {who}"
        elif kind == "card":
            text = f"{a.get('card', 'yellow').replace('_', ' ').capitalize()} card: {who}"
        elif kind == "stoppage" and a.get("reason") in ("offside", "ball_out"):
            text = {"offside": "Offside", "ball_out": "Ball out"}[a["reason"]]
        elif kind in ("half_end", "match_end"):
            text = "Half time" if kind == "half_end" else "Full time"
        if text:
            out.append([e.get("play_ms", 0), text, dict(score)])
    return out


def _jumps(story: dict) -> list[dict]:
    out = []
    for b in story["beats"]:
        if "minute" not in b or b["kind"] in ("half_end", "match_end"):
            continue
        t = max(0, b["minute"] * 60 + b.get("second", 0) - JUMP_LEAD_S)
        label = b.get("demo_moment", b["kind"]).replace("_", " ")
        out.append({"period": b["period"], "minute": t // 60, "second": t % 60, "label": f"{b['minute']}' {label}"})
    return out


def build_view(seed: int, out: Path, data_dir: Path = DATA_DIR) -> int:
    """Write the viewer for the reference match of `seed`; returns the number of frames."""
    ref = data_dir / "reference"
    lines = (ref / f"match-{seed:03d}.jsonl").read_text(encoding="utf-8").splitlines()
    meta = json.loads(lines[0])
    events = [json.loads(x) for x in lines[1:] if x.strip()]
    with gzip.open(ref / f"tracking-{seed:03d}.jsonl.gz", "rt", encoding="utf-8") as f:
        header = json.loads(f.readline())
        raw = [json.loads(line) for line in f]
    clubs = {c["team_id"]: c for c in json.loads((data_dir / "clubs.json").read_text(encoding="utf-8"))["clubs"]}
    story = next(s for s in map(load_storyline, sorted(data_dir.glob("storyline*.json"))) if s["seed"] == seed)

    home, away = meta["home"]["team_id"], meta["away"]["team_id"]
    players = {p["player_id"]: {"n": p["number"], "name": p["name"], "team": t["team_id"], "gk": p["position"] == "GK"}
               for t in (meta["home"], meta["away"]) for p in t["players"]}
    ids = sorted({pid for fr in raw for pid in fr["players"]})
    frames = []  # [play_ms, period, t_ms, ball x, y, z, then x, y per player id (-1 when off the pitch)]
    for fr in raw:
        row = [fr["play_ms"], fr["period"], fr["t_ms"], *fr["ball"]]
        for pid in ids:
            xy = fr["players"].get(pid)
            row += [round(xy[0], 1), round(xy[1], 1)] if xy else [-1, -1]
        frames.append(row)
    data = {"meta": {"home": meta["home"]["name"], "away": meta["away"]["name"], "venue": meta["venue"],
                     "homeId": home, "awayId": away,
                     "homeColor": clubs[home]["primary_color"], "awayColor": clubs[away]["primary_color"],
                     "homeText": clubs[home].get("secondary_color") or "#ffffff",
                     "awayText": clubs[away].get("secondary_color") or "#ffffff"},
            "ids": ids, "players": {pid: players[pid] for pid in ids}, "frames": frames,
            "captions": _captions(events, {pid: p["name"] for pid, p in players.items()}, home, away),
            "jumps": _jumps(story), "frameMs": header.get("frame_ms", 250)}
    out.parent.mkdir(parents=True, exist_ok=True)
    page = TEMPLATE.read_text(encoding="utf-8").replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
    out.write_text(page, encoding="utf-8")
    return len(frames)

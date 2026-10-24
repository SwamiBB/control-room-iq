"""Running distance per player from the tracking stream, so the stats engine can quote real totals.

Carry-only distance (runs with the ball) is a few hundred metres a match, far too low to quote. The tracking
stream (ball and 22 players at 4 Hz, data/reference/tracking-<seed>.jsonl.gz) has the off-ball running too.
On load the file is streamed once and each player's cumulative metres are kept as one float column (a few MB a
match, cached per file); `advance(play_ms)` then reads the value at that time. The header is checked first, so a
match without its own tracking file never loads one.

Loading still takes a moment (about 0.5-2 s depending on the machine): callers on an event loop should build the
StateFolder in a worker thread (asyncio.to_thread), or pass `tracking=` in explicitly.

A tracking file is used only when its header names the same match_id, so a free-play match with the same seed
never picks up the reference match's running. No tracking for a match means no distance, never a wrong one.
"""

from __future__ import annotations

import gzip
import json
import math
from array import array
from bisect import bisect_right
from functools import lru_cache
from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parents[3] / "data" / "reference"
M_PER_X, M_PER_Y = 1.05, 0.68  # 105 x 68 m pitch on the 0-100 grid


def _header(path: Path) -> dict:
    """Only the first line: cheap, so a free-play match never pays for loading frames it would throw away."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.loads(f.readline())


@lru_cache(maxsize=4)
def _load(path: str) -> tuple[array, dict[str, array]]:
    """(play_ms per frame, player id -> cumulative metres per frame), parsed as a stream: no list of frames is
    held, only one float column per player (a few MB a match), cached per file."""
    times = array("i")
    cols: dict[str, array] = {}
    total: dict[str, float] = {}
    last: dict[str, tuple[float, float]] = {}
    period = 1
    with gzip.open(path, "rt", encoding="utf-8") as f:
        f.readline()  # header
        for line in f:
            fr = json.loads(line)
            if fr["period"] != period:  # teams line up again for the second half: not running
                period, last = fr["period"], {}
            for pid, (x, y) in fr["players"].items():
                if pid not in cols:  # a substitute comes on: zero for every earlier frame
                    cols[pid], total[pid] = array("f", bytes(4 * len(times))), 0.0
                prev = last.get(pid)
                if prev is not None:
                    total[pid] += math.hypot((x - prev[0]) * M_PER_X, (y - prev[1]) * M_PER_Y)
                last[pid] = (x, y)
            times.append(fr["play_ms"])
            for pid, col in cols.items():
                col.append(total[pid])
    return times, cols


def find_tracking(match_id: str, seed: int, directory: Path = REFERENCE_DIR) -> TrackingDistances | None:
    path = directory / f"tracking-{seed:03d}.jsonl.gz"
    if not path.exists() or _header(path).get("match_id") != match_id:
        return None
    return TrackingDistances(*_load(str(path)))


class TrackingDistances:
    def __init__(self, times: array, cols: dict[str, array]) -> None:
        self._times, self._cols = times, cols

    def advance(self, play_ms: int) -> dict[str, float]:
        """Cumulative metres per player at play_ms (players who have not run yet are left out)."""
        i = bisect_right(self._times, play_ms) - 1
        if i < 0:
            return {}
        return {pid: float(col[i]) for pid, col in self._cols.items() if col[i] > 0}

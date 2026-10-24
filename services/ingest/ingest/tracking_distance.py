"""Running distance per player from the tracking stream, so the stats engine can quote real totals.

Carry-only distance (runs with the ball) is a few hundred metres a match, far too low to quote. The tracking
stream (ball and 22 players at 4 Hz, data/reference/tracking-<seed>.jsonl.gz) has the off-ball running too.
On load each player's cumulative metres are computed once per frame and kept in a flat float array (about 3 MB a
match); `advance(play_ms)` then reads the row at that time.

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


@lru_cache(maxsize=4)
def _load(path: str) -> tuple[dict, array, tuple[str, ...], array]:
    """(header, play_ms per frame, player ids, cumulative metres: one row of len(pids) per frame)."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        header = json.loads(f.readline())
        frames = [json.loads(line) for line in f]
    pids = tuple(sorted({pid for fr in frames for pid in fr["players"]}))
    slot = {pid: i for i, pid in enumerate(pids)}
    times, cum = array("i"), array("f")
    total = [0.0] * len(pids)
    last: dict[str, tuple[float, float]] = {}
    period = 1
    for fr in frames:
        if fr["period"] != period:  # teams line up again for the second half: not running
            period, last = fr["period"], {}
        for pid, (x, y) in fr["players"].items():
            prev = last.get(pid)
            if prev is not None:
                total[slot[pid]] += math.hypot((x - prev[0]) * M_PER_X, (y - prev[1]) * M_PER_Y)
            last[pid] = (x, y)
        times.append(fr["play_ms"])
        cum.extend(total)
    return header, times, pids, cum


def find_tracking(match_id: str, seed: int, directory: Path = REFERENCE_DIR) -> TrackingDistances | None:
    path = directory / f"tracking-{seed:03d}.jsonl.gz"
    if not path.exists():
        return None
    header, times, pids, cum = _load(str(path))
    return TrackingDistances(times, pids, cum) if header.get("match_id") == match_id else None


class TrackingDistances:
    def __init__(self, times: array, pids: tuple[str, ...], cum: array) -> None:
        self._times, self._pids, self._cum = times, pids, cum

    def advance(self, play_ms: int) -> dict[str, float]:
        """Cumulative metres per player at play_ms (players who have not run yet are left out)."""
        i = bisect_right(self._times, play_ms) - 1
        if i < 0:
            return {}
        row = i * len(self._pids)
        return {pid: float(self._cum[row + j]) for j, pid in enumerate(self._pids) if self._cum[row + j] > 0}

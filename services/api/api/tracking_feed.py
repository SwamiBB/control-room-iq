"""Ball and player positions for the viewers, from the match's tracking file.

The simulator writes a tracking stream for each reference match (data/reference/tracking-<seed>.jsonl.gz: the ball
and every player on the pitch, 4 times a second, in screen coordinates 0-100 with the ball's height in metres).
The stats engine reads the same file for running distance only (ingest/tracking_distance.py) and keeps no
positions, so the API reads it again here: the replay sends the frame at its play time to every viewer, and the
viewer draws the players and the ball behind the graphics.

The frames are kept as their JSON lines (about 13 MB for a full match) and parsed only when one is sent, a few
times a second. Like tracking_distance, a file is used only when its header names the same match, so a free-play
match never picks up a reference match's positions: no tracking means no frames, never wrong ones.

Positions are match data, not generated text: like the strike cue they need no operator approval.
"""

from __future__ import annotations

import gzip
import json
from array import array
from bisect import bisect_right
from functools import lru_cache
from pathlib import Path

from crq_schemas import MatchMeta

REFERENCE_DIR = Path(__file__).resolve().parents[3] / "data" / "reference"


class TrackingFeed:
    def __init__(self, times: array, lines: list[str]) -> None:
        self._times, self._lines = times, lines

    def index_at(self, play_ms: int) -> int | None:
        """The frame showing the match at play_ms: the last one at or before it, or None before the first."""
        i = bisect_right(self._times, play_ms) - 1
        return i if i >= 0 else None

    def frame(self, index: int) -> dict:
        """{frame, play_ms, period, t_ms, ball: [x, y, height_m], players: {player_id: [x, y]}}"""
        return json.loads(self._lines[index])


@lru_cache(maxsize=2)
def _load(path: str) -> tuple[array, list[str]]:
    """(play_ms per frame, the frames' JSON lines), cached per file so Run again does not read it twice."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        f.readline()  # header
        lines = [line for line in f.read().splitlines() if line.strip()]
    times = array("i", (json.loads(line)["play_ms"] for line in lines))
    return times, lines


def load_tracking(meta: MatchMeta, directory: Path = REFERENCE_DIR) -> TrackingFeed | None:
    path = directory / f"tracking-{meta.seed:03d}.jsonl.gz"
    if not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as f:
        if json.loads(f.readline()).get("match_id") != meta.match_id:
            return None
    return TrackingFeed(*_load(str(path)))

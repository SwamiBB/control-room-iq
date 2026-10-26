"""The viewers get the players and the ball from the match's tracking file, at the replay's play time."""

import asyncio
import gzip
import json
from pathlib import Path

import api.main as main
from api.main import ReplayRequest, _drive_replay, _pace, _send_tracking, hub
from api.packets import ViewerPrefs
from api.tracking_feed import load_tracking
from api_factories import RecordingSocket
from simulator.cli import build_meta
from simulator.engine import MatchEngine


def _frame(play_ms: int) -> dict:
    return {"frame": play_ms // 250, "play_ms": play_ms, "period": 1, "t_ms": play_ms, "ball": [50.0, 50.0, 0.0],
            "players": {"har-09": [40.0 + play_ms / 1000, 50.0], "nfu-09": [60.0, 50.0]}}


def _write_tracking(directory: Path, meta, until_ms: int, match_id: str | None = None) -> None:
    lines = [{"match_id": match_id or meta.match_id, "seed": meta.seed, "frame_ms": 250},
             *(_frame(t) for t in range(0, until_ms + 1, 250))]
    with gzip.open(directory / f"tracking-{meta.seed:03d}.jsonl.gz", "wt", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(x) for x in lines))


def _viewer() -> RecordingSocket:
    ws = RecordingSocket()
    hub.viewers[ws] = ViewerPrefs()
    return ws


def test_the_frame_at_a_play_time_is_the_last_one_at_or_before_it(tmp_path):
    meta = build_meta(7)
    _write_tracking(tmp_path, meta, 1000)
    feed = load_tracking(meta, tmp_path)
    assert feed is not None
    assert feed.frame(feed.index_at(0))["play_ms"] == 0
    assert feed.frame(feed.index_at(600))["play_ms"] == 500
    assert feed.frame(feed.index_at(10_000))["play_ms"] == 1000
    assert feed.frame(feed.index_at(600))["players"]["har-09"] == [40.5, 50.0]
    assert feed.index_at(-1) is None


def test_a_match_without_its_own_tracking_file_gets_none(tmp_path):
    meta = build_meta(7)
    assert load_tracking(meta, tmp_path) is None, "no file"
    _write_tracking(tmp_path, meta, 1000, match_id="m-free-play")
    assert load_tracking(meta, tmp_path) is None, "another match's file, same seed"


def test_pacing_sends_the_frame_where_the_match_is_not_where_the_clock_is(monkeypatch, tmp_path):
    # The clock already reads the next event's time while the gap is waited out; the frames follow the match.
    meta = build_meta(7)
    _write_tracking(tmp_path, meta, 2000)
    hub.tracking = load_tracking(meta, tmp_path)
    monkeypatch.setattr(main, "TRACKING_SEND_S", 0)
    viewer = _viewer()
    hub.clock.play_ms = 1000
    asyncio.run(_pace(1000, ReplayRequest(file="unused", speed=2.5)))  # 250 ms of play per 100 ms slice
    assert [m["frame"]["play_ms"] for m in viewer.of_type("tracking")] == [250, 500, 750, 1000]


def test_a_frame_goes_once_and_no_more_often_than_the_send_interval(tmp_path):
    meta = build_meta(7)
    _write_tracking(tmp_path, meta, 2000)
    hub.tracking = load_tracking(meta, tmp_path)
    viewer = _viewer()

    async def scenario():
        await _send_tracking(250)
        await _send_tracking(300)  # the same frame
        await _send_tracking(500)  # a new frame, but straight after the last send

    asyncio.run(scenario())
    assert [m["frame"]["play_ms"] for m in viewer.of_type("tracking")] == [250]


def _write_match(path: Path, events: int = 60):
    meta = build_meta(7)
    picked = [e for e in MatchEngine(meta).run() if e.period == 1][:events]
    path.write_text("\n".join([meta.model_dump_json(), *(e.model_dump_json() for e in picked)]), encoding="utf-8")
    return meta, picked[-1].play_ms


def test_a_replay_sends_its_viewers_the_frames_as_it_plays(monkeypatch, tmp_path):
    meta, last_ms = _write_match(tmp_path / "m.jsonl")
    _write_tracking(tmp_path, meta, last_ms + 5000)
    monkeypatch.setattr(main, "load_tracking", lambda m: load_tracking(m, tmp_path))
    monkeypatch.setattr(main, "TRACKING_SEND_S", 0)
    viewer = _viewer()
    asyncio.run(_drive_replay(ReplayRequest(file=str(tmp_path / "m.jsonl"), speed=1e6, min_importance=2.0)))
    played = [m["frame"]["play_ms"] for m in viewer.of_type("tracking")]
    assert len(played) > 3
    assert played == sorted(set(played)), "each frame once, in play order"
    assert played[-1] <= last_ms, "never ahead of the match"


def test_a_match_without_tracking_sends_no_frames(monkeypatch, tmp_path):
    _write_match(tmp_path / "m.jsonl")
    monkeypatch.setattr(main, "load_tracking", lambda m: load_tracking(m, tmp_path))  # no file there
    viewer = _viewer()
    asyncio.run(_drive_replay(ReplayRequest(file=str(tmp_path / "m.jsonl"), speed=1e6, min_importance=2.0)))
    assert viewer.of_type("tracking") == [] and hub.tracking is None

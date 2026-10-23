import asyncio
from pathlib import Path

from api.main import ReplayRequest, _replay, _stamp_play_time, hub
from api_factories import RecordingSocket, moment
from simulator.cli import build_meta
from simulator.engine import MatchEngine


def _write_match(path: Path, per_period: int = 40) -> Path:
    # Synthetic match from the repo's own simulator; v0.1 files carry no play_ms, which the clock must handle.
    meta = build_meta(7)
    events = list(MatchEngine(meta).run())
    picked = [e for e in events if e.period == 1][:per_period] + [e for e in events if e.period == 2][:per_period]
    lines = [meta.model_dump_json()] + [e.model_dump_json(exclude={"play_ms"}) for e in picked]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _replay_and_record(tmp_path: Path) -> list[dict]:
    console = RecordingSocket()
    hub.operators.add(console)
    path = _write_match(tmp_path / "m.jsonl")
    asyncio.run(_replay(ReplayRequest(file=str(path), speed=1e9, min_importance=2.0)))
    return console.sent


def test_replay_state_messages_carry_play_time_and_display_clock(tmp_path):
    states = [m for m in _replay_and_record(tmp_path) if m["type"] == "state"]
    assert states
    for msg in states:
        assert set(msg["clock"]) == {"period", "clock_ms", "play_ms"}
        assert msg["state"]["play_ms"] == msg["clock"]["play_ms"]
        assert msg["state"]["t_ms"] == msg["clock"]["clock_ms"]


def test_replay_play_time_is_monotonic_across_half_time(tmp_path):
    clocks = [m["clock"] for m in _replay_and_record(tmp_path) if m["type"] == "state"]
    plays = [c["play_ms"] for c in clocks]
    assert plays == sorted(plays)
    assert {c["period"] for c in clocks} == {1, 2}
    first_half_end = max(c["play_ms"] for c in clocks if c["period"] == 1)
    assert min(c["play_ms"] for c in clocks if c["period"] == 2) >= first_half_end


def test_stamp_play_time_fills_missing_play_ms_from_the_replay_clock():
    hub.clock.play_ms = 2_830_000
    assert _stamp_play_time(moment(play_ms=0)).play_ms == 2_830_000


def test_stamp_play_time_keeps_play_ms_set_by_ingest():
    hub.clock.play_ms = 2_830_000
    assert _stamp_play_time(moment(play_ms=1_234)).play_ms == 1_234

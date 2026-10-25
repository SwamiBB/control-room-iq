import asyncio
import time
from pathlib import Path

from api.main import (
    ReplayRequest,
    _drive_replay,
    _effective_speed,
    _pace,
    _replay,
    _stamp_play_time,
    hub,
)
from api_factories import RecordingSocket, moment, proposal
from crq_schemas import ProposalStatus
from simulator.cli import build_meta
from simulator.engine import MatchEngine


def _pick(per_period: int = 40) -> list:
    meta = build_meta(7)
    events = list(MatchEngine(meta).run())
    return [meta, *[e for e in events if e.period == 1][:per_period],
            *[e for e in events if e.period == 2][:per_period]]


def _write_match(path: Path, per_period: int = 40, with_play_ms: bool = False) -> Path:
    # Synthetic match from the repo's own simulator. v0.1 files carry no play_ms, which the clock must
    # handle; the reference files v0.2 writes do carry it, and windowing is specified in those terms.
    meta, *picked = _pick(per_period)
    dump = (lambda e: e.model_dump_json()) if with_play_ms else (lambda e: e.model_dump_json(exclude={"play_ms"}))
    path.write_text("\n".join([meta.model_dump_json(), *map(dump, picked)]), encoding="utf-8")
    return path


def _play_times(per_period: int = 40) -> list[int]:
    plays = [e.play_ms for e in _pick(per_period)[1:]]
    assert plays[0] < plays[-1], "the simulator stopped stamping play_ms; windowing tests are meaningless"
    return plays


def _replay_and_record(tmp_path: Path) -> list[dict]:
    console = RecordingSocket()
    hub.operators.add(console)
    path = _write_match(tmp_path / "m.jsonl")
    asyncio.run(_drive_replay(ReplayRequest(file=str(path), speed=1e9, min_importance=2.0)))
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


def test_a_window_replays_only_its_own_events(tmp_path):
    console = RecordingSocket()
    hub.operators.add(console)
    path = _write_match(tmp_path / "m.jsonl", with_play_ms=True)
    plays = _play_times()
    lo, hi = plays[len(plays) // 3], plays[2 * len(plays) // 3]
    asyncio.run(_drive_replay(ReplayRequest(file=str(path), speed=1e9, min_importance=2.0,
                                      from_play_ms=lo, to_play_ms=hi)))
    seen = [m["clock"]["play_ms"] for m in console.of_type("state")]
    assert seen and lo <= min(seen) and max(seen) <= hi


def test_the_warm_up_leaves_the_match_where_the_window_starts(tmp_path):
    """Skipping to a window must not skip the match that led to it: the state is folded first."""
    path = _write_match(tmp_path / "m.jsonl", with_play_ms=True)
    plays = _play_times()
    asyncio.run(_drive_replay(ReplayRequest(file=str(path), speed=1e9, min_importance=2.0,
                                      from_play_ms=plays[2 * len(plays) // 3])))
    skipped = hub.match_state

    asyncio.run(_drive_replay(ReplayRequest(file=str(path), speed=1e9, min_importance=2.0)))
    whole = hub.match_state
    assert skipped is not None and whole is not None and skipped is not whole
    assert (skipped.seq, skipped.home.goals, skipped.away.goals) == (whole.seq, whole.home.goals,
                                                                     whole.away.goals)


def test_the_match_slows_to_real_time_while_a_decision_is_on_the_desk():
    req = ReplayRequest(file="unused", speed=20, decision_speed=1)
    assert _effective_speed(req) == 20
    hub.proposals["p-1"] = proposal(status=ProposalStatus.PROPOSED)
    assert _effective_speed(req) == 1
    hub.proposals["p-1"] = proposal(status=ProposalStatus.AIRED)
    assert _effective_speed(req) == 20


def test_a_graphic_the_timer_has_held_lets_the_match_run_on():
    """The decision window closed when the timer acted; an unattended desk must not pin play at 1x."""
    req = ReplayRequest(file="unused", speed=20, decision_speed=1)
    hub.proposals["p-1"] = proposal(status=ProposalStatus.HELD)
    assert _effective_speed(req) == 20


def test_an_open_decision_runs_at_real_time_unless_that_is_turned_off():
    hub.proposals["p-1"] = proposal(status=ProposalStatus.PROPOSED)
    assert _effective_speed(ReplayRequest(file="unused", speed=20)) == 1, "real time is the default"
    assert _effective_speed(ReplayRequest(file="unused", speed=20, decision_speed=None)) == 20


def test_the_console_is_told_each_time_the_speed_changes():
    console = RecordingSocket()
    hub.operators.add(console)
    req = ReplayRequest(file="unused", speed=1e6, decision_speed=1e6)
    asyncio.run(_pace(1000, req))
    assert [m["speed"] for m in console.of_type("replay")] == [1e6], "one announcement, not one per slice"


def test_a_second_replay_starts_from_a_clear_desk(tmp_path):
    """Metrics and the decision log are per match; a re-run must not inherit the last one's."""
    path = _write_match(tmp_path / "m.jsonl")
    asyncio.run(_drive_replay(ReplayRequest(file=str(path), speed=1e9, min_importance=2.0)))
    hub.decisions.append(hub.decisions[0] if hub.decisions else _stale_entry())
    hub.packets.append("leftover")  # stand-ins: this test is about the clearing, not what produced them
    hub.proposals["p-old"] = proposal()

    asyncio.run(_drive_replay(ReplayRequest(file=str(path), speed=1e9, min_importance=2.0)))
    assert hub.decisions == [] and hub.packets == [] and hub.proposals == {}
    assert hub.deliveries == [] and hub.moments == {} and hub.results == {}


def _stale_entry():
    from crq_schemas import DecisionLogEntry
    return DecisionLogEntry(entry_id="d-old", match_id="m", proposal_id="p-old", action="aired",
                            actor="operator", at=hub.now())


def test_the_console_is_told_when_the_replay_ends(tmp_path):
    console = RecordingSocket()
    hub.operators.add(console)
    asyncio.run(_replay(ReplayRequest(file=str(_write_match(tmp_path / "m.jsonl")), speed=1e9,
                                      min_importance=2.0)))
    end = console.of_type("replay")[-1]
    assert end["finished"] is True and end["error"] is None and end["speed"] is None
    assert hub.replay_speed is None


def test_a_replay_that_fails_says_so_instead_of_stopping_in_silence():
    console = RecordingSocket()
    hub.operators.add(console)
    asyncio.run(_replay(ReplayRequest(file="no/such/match.jsonl")))
    end = console.of_type("replay")[-1]
    assert end["finished"] is True and "FileNotFoundError" in end["error"]


class TimedSocket(RecordingSocket):
    def __init__(self) -> None:
        super().__init__()
        self.at: list[float] = []

    async def send_json(self, msg: dict) -> None:
        await super().send_json(msg)
        self.at.append(time.monotonic())


def test_at_real_time_state_goes_out_on_the_clock_not_the_event_count(tmp_path):
    """At speed 1 ten events can take seconds; the console's play clock must not freeze waiting for them."""
    meta, *events = _pick(12)
    # 100 ms of play apart, and no seq a multiple of ten, so only a real-time throttle publishes anything.
    events = [e.model_copy(update={"seq": 10 * i + 1, "period": 1, "t_ms": 100 * (i + 1), "play_ms": 100 * (i + 1)})
              for i, e in enumerate(events[:12])]
    path = tmp_path / "m.jsonl"
    path.write_text("\n".join([meta.model_dump_json(), *(e.model_dump_json() for e in events)]), encoding="utf-8")
    console = TimedSocket()
    hub.operators.add(console)

    asyncio.run(_drive_replay(ReplayRequest(file=str(path), speed=1, min_importance=2.0)))
    at = [t for t, m in zip(console.at, console.sent, strict=True) if m["type"] == "state"]
    assert len(at) >= 3
    gaps = [b - a for a, b in zip(at, at[1:], strict=False)]
    assert max(gaps) < 0.6, f"state gaps {gaps}: bounded by 250 ms plus one event, not by ten events"


def test_stamp_play_time_fills_missing_play_ms_from_the_replay_clock():
    hub.clock.play_ms = 2_830_000
    assert _stamp_play_time(moment(play_ms=0)).play_ms == 2_830_000


def test_stamp_play_time_keeps_play_ms_set_by_ingest():
    hub.clock.play_ms = 2_830_000
    assert _stamp_play_time(moment(play_ms=1_234)).play_ms == 1_234

"""Tracking-style position stream for the pitch view: ball and every player on the pitch, 4 times a second.

Derived from the event stream and deterministic per seed. Each player has a formation slot; the team
stretches in possession and compacts toward the ball out of it, the player on the ball runs to it, the
keeper follows the ball a little, and a slow drift keeps everyone moving. Steps are capped by a speed
from the player's pace. Not physics: enough for a broadcast-style top-down view and realistic running
totals.

Output coordinates are absolute (screen) coordinates, 0-100: the home team attacks toward x = 100 in the
first half and toward x = 0 in the second.
"""

from __future__ import annotations

import gzip
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crq_schemas import EventType, MatchEvent, MatchMeta, Player

from .scripted import FRAME_MS, frame_index, play_ms, stream

# One tick: {frame, play_ms, period, t_ms, ball: [x, y], players: {player_id: [x, y]}}. Plain JSON, not a
# contract model: only the pitch view reads it.
Frame = dict[str, Any]

M_PER_X, M_PER_Y = 1.05, 0.68  # 105 x 68 m pitch on a 0-100 grid
GROUP = {"GK": 0, "DF": 1, "MF": 2, "FW": 3}
# Slots in the team's own attacking frame (x toward the opponent's goal), ordered GK, DF, MF, FW.
SLOTS = {
    "4-3-3": [(6, 50), (25, 15), (22, 38), (22, 62), (25, 85), (45, 30), (42, 50), (45, 70), (68, 20), (72, 50),
              (68, 80)],
    "4-2-3-1": [(6, 50), (25, 15), (22, 38), (22, 62), (25, 85), (40, 38), (40, 62), (58, 20), (58, 50), (58, 80),
                (72, 50)],
    "3-5-2": [(6, 50), (22, 28), (20, 50), (22, 72), (45, 10), (42, 35), (40, 50), (42, 65), (45, 90), (70, 40),
              (70, 60)],
}
ON_BALL = {EventType.PASS, EventType.CARRY, EventType.SHOT_TAKEN, EventType.SHOT, EventType.KICKOFF,
           EventType.POSSESSION_CHANGE, EventType.INTERCEPTION, EventType.TACKLE}
DRIFT_X, DRIFT_Y = 2.4, 3.2  # amplitude of the slow drift, grid units


@dataclass
class _Mover:
    player_id: str
    team: str
    slot: tuple[float, float]
    keeper: bool
    vmax: float  # m/s
    x: float
    y: float
    phase_a: float
    phase_b: float
    per_a: float
    per_b: float
    dist_m: float = 0.0
    top_kmh: float = 0.0


def _attacks_right(team_id: str, home_id: str, period: int) -> bool:
    return (team_id == home_id) == (period == 1)


def _to_abs(right: bool, x: float, y: float) -> tuple[float, float]:
    return (x, y) if right else (100 - x, 100 - y)


def _ball_keys(events: list[MatchEvent], home_id: str, period: int) -> list[tuple[int, float, float]]:
    keys: list[tuple[int, float, float]] = []
    for e in events:
        if e.period != period or e.x is None or e.y is None or e.team is None or e.type == EventType.PRESSURE:
            continue
        right = _attacks_right(e.team, home_id, period)
        keys.append((e.t_ms, *_to_abs(right, e.x, e.y)))
        if e.end_x is not None and e.end_y is not None:
            dist_m = math.hypot((e.end_x - e.x) * M_PER_X, (e.end_y - e.y) * M_PER_Y)
            speed = (e.attrs.get("ball_speed_kmh") or e.attrs.get("speed_kmh") or 60) / 3.6
            keys.append((e.t_ms + int(1000 * dist_m / max(speed, 3.0)), *_to_abs(right, e.end_x, e.end_y)))
    keys.sort(key=lambda k: k[0])
    return keys or [(0, 50.0, 50.0)]


def _mover(p: Player, team_id: str, slot: tuple[float, float], rng) -> _Mover:
    return _Mover(player_id=p.player_id, team=team_id, slot=slot, keeper=p.position == "GK",
                  vmax=7.0 + 2.5 * p.pace, x=slot[0], y=slot[1],
                  phase_a=rng.uniform(0, 2 * math.pi), phase_b=rng.uniform(0, 2 * math.pi),
                  per_a=rng.uniform(3000, 6000), per_b=rng.uniform(3000, 6000))


def _target(m: _Mover, right: bool, in_possession: bool, ball: tuple[float, float], t: int) -> tuple[float, float]:
    bx, by = _to_abs(right, *ball)  # the ball in this team's own frame (the transform is its own inverse)
    sx, sy = m.slot
    if m.keeper:
        tx, ty = (3.6 if bx < 33 else 3.6 + (bx - 33) * 0.08), 50 + (by - 50) * 0.1
    elif in_possession:  # ball weights calibrated to ~11 km per outfield player (docs/CALIBRATION.md)
        tx = sx * 0.65 + bx * 0.35 + 6 + DRIFT_X * math.sin(t / m.per_a + m.phase_a)
        ty = sy * 0.88 + by * 0.12 + DRIFT_Y * math.sin(t / m.per_b + m.phase_b)
    else:
        tx = sx * 0.68 + bx * 0.32 - 8 + DRIFT_X * math.sin(t / m.per_a + m.phase_a)
        ty = sy * 0.68 + by * 0.32 + DRIFT_Y * math.sin(t / m.per_b + m.phase_b)
    return _to_abs(right, min(max(tx, 1.0), 99.0), min(max(ty, 1.0), 99.0))


def _step(m: _Mover, tx: float, ty: float, dt_s: float) -> None:
    want = math.hypot((tx - m.x) * M_PER_X, (ty - m.y) * M_PER_Y)
    if want <= 1e-6:
        return
    step = min(want * 0.35, m.vmax * dt_s)
    ratio = step / want
    m.x += (tx - m.x) * ratio
    m.y += (ty - m.y) * ratio
    m.dist_m += step
    m.top_kmh = max(m.top_kmh, step / dt_s * 3.6)


def build_tracking(meta: MatchMeta, events: list[MatchEvent]) -> tuple[list[Frame], dict[str, dict[str, float]]]:
    """Return the frames and a per-player summary {distance_km, top_speed_kmh}."""
    rng = stream(meta.seed, "tracking")
    home = meta.home.team_id
    p1_end = next(e.t_ms for e in events if e.type == EventType.HALF_END)
    players = {p.player_id: p for t in (meta.home, meta.away) for p in t.players}
    on_pitch: dict[str, _Mover] = {}
    for team in (meta.home, meta.away):
        starters = sorted((p for p in team.players if p.number <= 11), key=lambda p: (GROUP[p.position], p.number))
        for p, slot in zip(starters, SLOTS.get(team.formation, SLOTS["4-3-3"]), strict=True):  # 11 and 11
            on_pitch[p.player_id] = _mover(p, team.team_id, slot, rng)
    finished: dict[str, _Mover] = {}
    changes = [e for e in events if e.type == EventType.SUBSTITUTION
               or (e.type == EventType.CARD and e.attrs.get("card") in ("red", "second_yellow"))]
    dt_s = FRAME_MS / 1000
    frames: list[Frame] = []
    ci = 0
    for period in (1, 2):
        keys = _ball_keys(events, home, period)
        touches = [(e.t_ms, e.team, e.player) for e in events if e.period == period and e.type in ON_BALL and e.team]
        end = max(e.t_ms for e in events if e.period == period)
        for m in on_pitch.values():  # line up in the team's own half for the kickoff
            right = _attacks_right(m.team, home, period)
            m.x, m.y = _to_abs(right, m.slot[0] * 0.5, m.slot[1])
        possession, actor, actor_t = touches[0][1] if touches else home, None, -10**9
        ki = ti = 0
        for t in range(0, end + 1, FRAME_MS):
            while ci < len(changes) and (changes[ci].period, changes[ci].t_ms) <= (period, t):
                c = changes[ci]
                if c.type == EventType.SUBSTITUTION and c.attrs["off"] in on_pitch:
                    off = on_pitch.pop(c.attrs["off"])
                    finished[off.player_id] = off
                    new = _mover(players[c.attrs["on"]], off.team, off.slot, rng)
                    new.x, new.y = off.x, off.y
                    on_pitch[new.player_id] = new
                elif c.player in on_pitch:
                    finished[c.player] = on_pitch.pop(c.player)
                ci += 1
            while ti < len(touches) and touches[ti][0] <= t:
                _, possession, actor = touches[ti]
                actor_t = touches[ti][0]
                ti += 1
            while ki + 1 < len(keys) and keys[ki + 1][0] <= t:
                ki += 1
            k0 = keys[ki]
            k1 = keys[ki + 1] if ki + 1 < len(keys) else k0
            f = 0.0 if k1[0] == k0[0] else min(1.0, max(0.0, (t - k0[0]) / (k1[0] - k0[0])))
            ball = (k0[1] + (k1[1] - k0[1]) * f, k0[2] + (k1[2] - k0[2]) * f)
            for m in on_pitch.values():
                if m.player_id == actor and t - actor_t < 2500:
                    tx, ty = ball
                else:
                    tx, ty = _target(m, _attacks_right(m.team, home, period), possession == m.team, ball, t)
                _step(m, tx, ty, dt_s)
            frames.append({"frame": frame_index(period, t, p1_end), "play_ms": play_ms(period, t, p1_end),
                           "period": period, "t_ms": t, "ball": [round(ball[0], 2), round(ball[1], 2)],
                           "players": {pid: [round(m.x, 2), round(m.y, 2)] for pid, m in on_pitch.items()}})
    summary = {pid: {"distance_km": round(m.dist_m / 1000, 2), "top_speed_kmh": round(m.top_kmh, 1)}
               for pid, m in {**finished, **on_pitch}.items()}
    return frames, summary


def write_tracking(path: Path, frames: list[Frame], meta: MatchMeta) -> None:
    """First line {match_id, seed, frame_ms}, then one frame per line, like a match file's MatchMeta header.
    gzip with mtime=0 so the same seed writes a byte-identical file."""
    with open(path, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        header = {"match_id": meta.match_id, "seed": meta.seed, "frame_ms": FRAME_MS}
        gz.write((json.dumps(header, separators=(",", ":")) + "\n").encode("utf-8"))
        for fr in frames:
            gz.write((json.dumps(fr, separators=(",", ":")) + "\n").encode("utf-8"))

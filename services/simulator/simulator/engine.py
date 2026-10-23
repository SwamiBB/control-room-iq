"""Deterministic, seedable synthetic football match engine.

Design goals:
- Football-realistic distributions (pass volume, completion, shot counts, xG, pressure phases).
- Fully deterministic for a given seed and squads, so ground truth is reproducible for evaluation.
- Produces `MatchEvent` records in match-clock order with pitch coordinates and type-specific attrs.

This is intentionally a possession-phase model rather than a physics engine: each phase is a
sequence of passes/carries that ends in a shot, a turnover, or a foul. It is enough to drive
statistics, moment detection, and narratives, and it is cheap to run at 100x speed.
"""

from __future__ import annotations

import math
import random
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

from crq_schemas import EventType, MatchEvent, MatchMeta, Team

PITCH_LEN = 100.0
PITCH_WID = 100.0
PERIOD_MS = 45 * 60 * 1000


@dataclass
class _Phase:
    team: Team
    opp: Team
    x: float
    y: float
    passes: int = 0
    events: list[MatchEvent] = field(default_factory=list)


class MatchEngine:
    def __init__(self, meta: MatchMeta) -> None:
        self.meta = meta
        self.rng = random.Random(meta.seed)
        self.seq = 0
        self.period = 1
        self.t_ms = 0
        self.play_offset = 0  # play_ms of the current period's kickoff (v0.2: play time never restarts)
        self.score = {meta.home.team_id: 0, meta.away.team_id: 0}
        self._minutes_played = {p.player_id: 0 for t in (meta.home, meta.away) for p in t.players}

    # ---------- helpers ----------
    def _evt(self, type_: EventType, team: Team | None = None, player: str | None = None, **kw) -> MatchEvent:
        self.seq += 1
        ev = MatchEvent(
            event_id=f"{self.meta.match_id}-{self.seq:05d}",
            match_id=self.meta.match_id,
            seq=self.seq,
            play_ms=self.play_offset + self.t_ms,
            t_ms=self.t_ms,
            period=self.period,  # type: ignore[arg-type]
            type=type_,
            team=team.team_id if team else None,
            player=player,
            **kw,
        )
        return ev

    def _tick(self, lo_ms: int, hi_ms: int) -> None:
        self.t_ms += self.rng.randint(lo_ms, hi_ms)

    def _pick(self, team: Team, weights: dict[str, float]) -> str:
        players = [p for p in team.players if p.position != "GK"]
        w = [weights.get(p.position, 1.0) for p in players]
        return self.rng.choices(players, weights=w, k=1)[0].player_id

    def _player(self, team: Team, pid: str):
        return next(p for p in team.players if p.player_id == pid)

    @staticmethod
    def _dist(x0: float, y0: float, x1: float, y1: float) -> float:
        # pitch is ~105m x 68m; scale 0-100 coords to meters
        return math.hypot((x1 - x0) * 1.05, (y1 - y0) * 0.68)

    @staticmethod
    def _xg(x: float, y: float, kind: str) -> float:
        # simple logistic on distance and angle to goal at (100, 50)
        d = math.hypot((100 - x) * 1.05, (50 - y) * 0.68)
        ang = abs(math.atan2((50 - y) * 0.68, (100 - x) * 1.05))
        base = 1 / (1 + math.exp(0.22 * d - 2.2 + 1.6 * ang))
        if kind == "header":
            base *= 0.6
        return round(min(max(base, 0.01), 0.95), 3)

    # ---------- phases ----------
    def _pressure_prob(self, team: Team, opp: Team) -> float:
        base = {"press": 0.42, "possession": 0.18, "direct": 0.22, "counter": 0.28}[opp.style]
        return base

    def _run_phase(self, team: Team, opp: Team, x: float, y: float) -> tuple[Team, float, float, list[MatchEvent]]:
        """Run one possession phase; return next team in possession, start coords, and events."""
        out: list[MatchEvent] = []
        pid = self._pick(team, {"DF": 1.2, "MF": 1.6, "FW": 0.8})
        for _ in range(60):
            p = self._player(team, pid)
            # pressure on the ball carrier?
            if self.rng.random() < self._pressure_prob(team, opp) * (1.3 if x > 55 else 0.8):
                presser = self._pick(opp, {"MF": 1.5, "FW": 1.3, "DF": 0.9})
                intensity = round(self.rng.uniform(0.3, 1.0), 2)
                out.append(self._evt(EventType.PRESSURE, opp, presser, x=100 - x, y=100 - y,
                                     attrs={"intensity": intensity, "target": pid}))
                if self.rng.random() < 0.18 * intensity:
                    out.append(self._evt(EventType.TACKLE, opp, presser, x=100 - x, y=100 - y, outcome="success",
                                         attrs={"won": True}))
                    out.append(self._evt(EventType.POSSESSION_CHANGE, opp, presser, x=100 - x, y=100 - y,
                                         attrs={"reason": "tackle"}))
                    self._tick(1500, 4000)
                    return opp, 100 - x, 100 - y, out

            # choose action: shoot if in range, else pass or carry
            shoot_p = 0.0
            if x > 80:
                shoot_p = 0.06 + 0.22 * p.shooting * (1 if abs(y - 50) < 20 else 0.4)
            r = self.rng.random()
            if r < shoot_p:
                kind = "header" if self.rng.random() < 0.15 else "foot"
                xg = self._xg(x, y, kind)
                speed = round(self.rng.uniform(70, 125) * (0.7 if kind == "header" else 1.0), 1)
                roll = self.rng.random()
                keeper = next(q for q in opp.players if q.position == "GK")
                # bands calibrated so about a third of shots are on target (docs/CALIBRATION.md)
                if roll < xg:
                    outcome = "goal"
                elif roll < xg + 0.26:
                    outcome = "saved"
                elif roll < xg + 0.45:
                    outcome = "blocked"
                else:
                    outcome = "off_target"
                out.append(self._evt(EventType.SHOT, team, pid, x=x, y=y, end_x=100, end_y=50 + self.rng.uniform(-4, 4),
                                     outcome=outcome, attrs={"xg": xg, "speed_kmh": speed, "body": kind,
                                                             "keeper": keeper.player_id}))
                self._tick(8000, 25000)
                if outcome == "goal":
                    self.score[team.team_id] += 1
                    out.append(self._evt(EventType.KICKOFF, opp, None, x=50, y=50, attrs={"after": "goal"}))
                    self._tick(30000, 60000)
                    return opp, 50, 50, out
                out.append(self._evt(EventType.POSSESSION_CHANGE, opp, keeper.player_id, x=5, y=50,
                                     attrs={"reason": outcome}))
                return opp, 8, 50, out

            if r < shoot_p + 0.25 and x < 85:
                # carry
                dx = self.rng.uniform(3, 14) * (0.6 + p.pace)
                dy = self.rng.uniform(-8, 8)
                nx, ny = min(x + dx, 95), min(max(y + dy, 2), 98)
                dist = self._dist(x, y, nx, ny)
                speed = round(18 + 14 * p.pace + self.rng.uniform(-2, 3), 1)
                out.append(self._evt(EventType.CARRY, team, pid, x=x, y=y, end_x=nx, end_y=ny, outcome="success",
                                     attrs={"distance_m": round(dist, 1), "speed_kmh": speed}))
                self._tick(int(dist / (speed / 3.6) * 1000) + 300, int(dist / (speed / 3.6) * 1000) + 1500)
                x, y = nx, ny
                continue

            # pass
            recv = self._pick(team, {"DF": 0.7 if x > 40 else 1.3, "MF": 1.6, "FW": 1.0 if x > 50 else 0.6})
            while recv == pid:
                recv = self._pick(team, {"MF": 1.0})
            forward_bias = 0.6 if team.style in ("direct", "counter") else 0.35
            dx = self.rng.uniform(-10, 30) if self.rng.random() < forward_bias else self.rng.uniform(-18, 12)
            dy = self.rng.uniform(-30, 30)
            nx, ny = min(max(x + dx, 3), 97), min(max(y + dy, 2), 98)
            dist = self._dist(x, y, nx, ny)
            difficulty = round(min(1.0, 0.15 + dist / 60 + (0.25 if nx > 75 else 0) + (0.2 if dx > 15 else 0)), 2)
            success_p = 0.93 - 0.55 * difficulty + 0.25 * p.passing
            ok = self.rng.random() < success_p
            out.append(self._evt(EventType.PASS, team, pid, x=x, y=y, end_x=nx, end_y=ny,
                                 outcome="success" if ok else "fail",
                                 attrs={"receiver": recv, "distance_m": round(dist, 1), "difficulty": difficulty,
                                        "progressive": dx > 10, "ball_speed_kmh": round(30 + dist * 0.9, 1)}))
            self._tick(int(dist * 60) + 1300, int(dist * 60) + 4300)
            if not ok:
                inter = self._pick(opp, {"DF": 1.4, "MF": 1.2})
                out.append(self._evt(EventType.INTERCEPTION, opp, inter, x=100 - nx, y=100 - ny, outcome="success"))
                out.append(self._evt(EventType.POSSESSION_CHANGE, opp, inter, x=100 - nx, y=100 - ny,
                                     attrs={"reason": "interception"}))
                return opp, 100 - nx, 100 - ny, out
            x, y, pid = nx, ny, recv
            if self.rng.random() < 0.024:
                fouler = self._pick(opp, {"DF": 1.3, "MF": 1.0})
                out.append(self._evt(EventType.FOUL, opp, fouler, x=100 - x, y=100 - y,
                                     attrs={"card": "yellow" if self.rng.random() < 0.16 else None}))
                if out[-1].attrs["card"]:
                    out.append(self._evt(EventType.CARD, opp, fouler, attrs={"card": "yellow"}))
                self._tick(20000, 45000)
                return team, x, y, out
        return opp, 50, 50, out

    # ---------- public ----------
    def run(self) -> Iterator[MatchEvent]:
        home, away = self.meta.home, self.meta.away
        for period in (1, 2):
            if period == 2:
                self.play_offset += self.t_ms  # the second half continues from the end of the first
            self.period = period
            self.t_ms = 0
            team, opp = (home, away) if period == 1 else (away, home)
            yield self._evt(EventType.KICKOFF, team, None, x=50, y=50, attrs={"period": period})
            x, y = 50.0, 50.0
            end_ms = PERIOD_MS + self.rng.randint(60000, 5 * 60000)
            while self.t_ms < end_ms:
                nxt, x, y, evs = self._run_phase(team, opp, x, y)
                yield from evs
                team, opp = nxt, (home if nxt is away else away)
                if period == 2 and 60 * 60000 < self.t_ms < 62 * 60000 and self.rng.random() < 0.5:
                    for t in (home, away):
                        bench = [p for p in t.players if p.number > 11][:1]
                        starters = [p for p in t.players if p.number <= 11 and p.position != "GK"]
                        if bench and starters:
                            off = self.rng.choice(starters)
                            yield self._evt(EventType.SUBSTITUTION, t, bench[0].player_id,
                                            attrs={"off": off.player_id, "on": bench[0].player_id})
            yield self._evt(EventType.HALF_END if period == 1 else EventType.MATCH_END, None, None,
                            attrs={"score": dict(self.score)})


def new_match_id() -> str:
    return "m-" + uuid.uuid4().hex[:8]

"""Fold MatchEvents into MatchState and detect Moments.

Pure functions, no I/O: the same code runs in unit tests, in the Event Hubs consumer, and in the
API's local replay mode. Everything here is deterministic ground truth that the agents are later
evaluated against.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from crq_schemas import EventType, MatchEvent, MatchMeta, MatchState, Moment, MomentKind, PlayerStats, TeamStats

SPEED_THRESHOLD_KMH = 32.0
BIG_CHANCE_XG = 0.30
MOMENTUM_SHIFT_DELTA = 0.6
PRESSURE_SPIKE_PER_MIN = 9


@dataclass
class StateFolder:
    meta: MatchMeta
    state: MatchState = field(init=False)
    _poss_ms: dict[str, int] = field(default_factory=dict)
    _last_poss_team: str | None = None
    _last_t: int = 0
    _recent: deque = field(default_factory=lambda: deque(maxlen=60))  # (t_ms, team, weight)
    _pressure_min: dict[int, int] = field(default_factory=dict)
    _moment_n: int = 0

    def __post_init__(self) -> None:
        h, a = self.meta.home.team_id, self.meta.away.team_id
        self.state = MatchState(match_id=self.meta.match_id, seq=0, period=1, t_ms=0,
                                home=TeamStats(team=h), away=TeamStats(team=a))
        for t in (self.meta.home, self.meta.away):
            for p in t.players:
                self.state.players[p.player_id] = PlayerStats(player_id=p.player_id, team=t.team_id)
        self._poss_ms = {h: 0, a: 0}

    def _team(self, team_id: str) -> TeamStats:
        return self.state.home if team_id == self.state.home.team else self.state.away

    def _sign(self, team_id: str) -> float:
        return 1.0 if team_id == self.state.home.team else -1.0

    def apply(self, ev: MatchEvent) -> list[Moment]:
        s = self.state
        if ev.period != s.period:
            self._last_t = 0
        s.period, s.t_ms, s.seq, s.last_event_id = ev.period, ev.t_ms, ev.seq, ev.event_id
        moments: list[Moment] = []
        # possession clock
        if self._last_poss_team:
            self._poss_ms[self._last_poss_team] += max(0, ev.t_ms - self._last_t)
        self._last_t = ev.t_ms
        if ev.team and ev.type in (EventType.PASS, EventType.CARRY, EventType.SHOT, EventType.KICKOFF,
                                   EventType.POSSESSION_CHANGE):
            self._last_poss_team = ev.team
        total = sum(self._poss_ms.values()) or 1
        s.home.possession_pct = round(100 * self._poss_ms[s.home.team] / total, 1)
        s.away.possession_pct = round(100 - s.home.possession_pct, 1)

        ps = s.players.get(ev.player) if ev.player else None
        ts = self._team(ev.team) if ev.team else None

        if ev.type == EventType.PASS and ts and ps:
            ts.passes += 1
            ps.passes += 1
            ok = ev.outcome == "success"
            if ok:
                ts.passes_completed += 1
                ps.passes_completed += 1
            self._recent.append((ev.t_ms, ev.team, 0.15 if ev.attrs.get("progressive") else 0.05))
        elif ev.type == EventType.CARRY and ps:
            ps.distance_m += ev.attrs.get("distance_m", 0)
            spd = ev.attrs.get("speed_kmh", 0)
            if spd > ps.top_speed_kmh:
                ps.top_speed_kmh = spd
                if spd >= SPEED_THRESHOLD_KMH:
                    moments.append(self._moment(ev, MomentKind.SPEED_THRESHOLD, 0.35,
                                                f"{self._name(ev.player)} hits {spd} km/h"))
        elif ev.type == EventType.SHOT and ts and ps:
            xg = float(ev.attrs.get("xg", 0))
            ts.shots += 1
            ps.shots += 1
            ts.xg = round(ts.xg + xg, 3)
            ps.xg = round(ps.xg + xg, 3)
            if ev.outcome in ("goal", "saved"):
                ts.shots_on_target += 1
            self._recent.append((ev.t_ms, ev.team, 0.5 + xg))
            if ev.outcome == "goal":
                ts.goals += 1
                ps.goals += 1
                moments.append(self._moment(ev, MomentKind.GOAL, 1.0,
                                            f"GOAL {self._name(ev.player)} ({ev.attrs.get('body')}, xG {xg})"))
            elif xg >= BIG_CHANCE_XG:
                moments.append(self._moment(ev, MomentKind.BIG_CHANCE, 0.6 + xg / 3,
                                            f"Big chance {self._name(ev.player)} {ev.outcome} (xG {xg})"))
        elif ev.type == EventType.PRESSURE and ts and ps:
            ts.pressures += 1
            ps.pressures += 1
            m = ev.t_ms // 60000 + (45 if ev.period == 2 else 0)
            self._pressure_min[m] = self._pressure_min.get(m, 0) + 1
            if self._pressure_min[m] == PRESSURE_SPIKE_PER_MIN:
                summary = f"{self._tname(ev.team)} pressing hard: {PRESSURE_SPIKE_PER_MIN} pressures in a minute"
                moments.append(self._moment(ev, MomentKind.PRESSURE_SPIKE, 0.5, summary))
        elif ev.type == EventType.TACKLE and ps:
            ps.tackles += 1
            self._recent.append((ev.t_ms, ev.team, 0.1))
        elif ev.type == EventType.CARD:
            moments.append(self._moment(ev, MomentKind.CARD, 0.45, f"Yellow card {self._name(ev.player)}"))
        elif ev.type == EventType.HALF_END:
            moments.append(self._moment(ev, MomentKind.HALF_END, 0.8, "Half time"))
        elif ev.type == EventType.MATCH_END:
            moments.append(self._moment(ev, MomentKind.MATCH_END, 1.0, "Full time"))

        # momentum: weighted recent actions, decayed over the last ~3 minutes
        now = ev.t_ms
        num = sum(w * self._sign(t) * max(0.0, 1 - (now - tm) / 180000) for tm, t, w in self._recent)
        den = sum(w * max(0.0, 1 - (now - tm) / 180000) for tm, t, w in self._recent) or 1
        mom = round(max(-1.0, min(1.0, num / den)), 3)
        minute = ev.t_ms // 60000 + (45 if ev.period == 2 else 0)
        if len(s.momentum) <= minute:
            prev = s.momentum[-1] if s.momentum else 0.0
            s.momentum.extend([prev] * (minute - len(s.momentum)) + [mom])
            if abs(mom - prev) >= MOMENTUM_SHIFT_DELTA and ev.type != EventType.KICKOFF:
                who = self._tname(s.home.team if mom > prev else s.away.team)
                moments.append(self._moment(ev, MomentKind.MOMENTUM_SHIFT, 0.55, f"Momentum swings to {who}"))
        else:
            s.momentum[minute] = mom
        # ppda per team (passes allowed per defensive action)
        for me, them in ((s.home, s.away), (s.away, s.home)):
            da = me.pressures * 0.25 + sum(p.tackles for p in s.players.values() if p.team == me.team)
            me.ppda = round(them.passes / da, 1) if da else None
        # milestones
        if ps and ps.passes in (50, 100) and ev.type == EventType.PASS:
            summary = f"{self._name(ev.player)} reaches {ps.passes} passes"
            moments.append(self._moment(ev, MomentKind.MILESTONE, 0.3, summary))
        return moments

    def _moment(self, ev: MatchEvent, kind: MomentKind, importance: float, summary: str) -> Moment:
        self._moment_n += 1
        return Moment(moment_id=f"{self.meta.match_id}-mo{self._moment_n:04d}", match_id=self.meta.match_id,
                      t_ms=ev.t_ms, period=ev.period, kind=kind, importance=round(min(1.0, importance), 2),
                      team=ev.team, player=ev.player, event_ids=[ev.event_id], summary=summary,
                      state=self.state.model_copy(deep=True))

    def _name(self, pid: str | None) -> str:
        for t in (self.meta.home, self.meta.away):
            for p in t.players:
                if p.player_id == pid:
                    return p.name
        return pid or "?"

    def _tname(self, tid: str | None) -> str:
        return self.meta.home.name if tid == self.meta.home.team_id else self.meta.away.name

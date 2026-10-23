"""Fold MatchEvents into MatchState and detect Moments.

Pure functions, no I/O: the same code runs in unit tests, in the Event Hubs consumer, and in the
API's local replay mode. Everything here is deterministic ground truth that the agents are later
evaluated against.

Beyond the running stats, the folder keeps the derived state the brief asks for (shot ledger, 5-minute
windows, pressure trend, momentum label, zones, phase, last stoppage, recap points, player focus,
milestones) and gives every Moment its beat, priority and snapshot: the only slice the agents see.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from crq_schemas import (EventType, MatchEvent, MatchMeta, MatchState, Milestone, Moment, MomentKind, PhaseSummary,
                         PlayerFocus, PlayerStats, PressureTrend, RecapPoint, ShotLedgerEntry, StoppageSummary,
                         TeamStats, TeamWindow)

from .derive import (BIG_CHANCE_XG, PRIORITY, WINDOW_MS, chance_quality, hold_advice, momentum_label,
                     stoppage_importance, zone)

SPEED_THRESHOLD_KMH = 32.0
MOMENTUM_SHIFT_DELTA = 0.6
PRESSURE_SPIKE_PER_MIN = 9
SPRINT_KMH = 25.0


@dataclass
class StateFolder:
    meta: MatchMeta
    state: MatchState = field(init=False)
    crowd_level: float = 0.35
    _poss_ms: dict[str, int] = field(default_factory=dict)
    _last_poss_team: str | None = None
    _last_t: int = 0
    _recent: deque = field(default_factory=lambda: deque(maxlen=60))  # (t_ms, team, weight)
    _pressure_min: dict[int, int] = field(default_factory=dict)
    _moment_n: int = 0
    _shots: list[tuple[int, int, str, float, str]] = field(default_factory=list)  # period, t, team, xg, event_id
    _high_press: list[tuple[int, int, str]] = field(default_factory=list)  # pressures in the opponent's half
    _stoppages: dict[str, list[MatchEvent]] = field(default_factory=dict)
    _phase_events: list[MatchEvent] = field(default_factory=list)
    _cards: dict[str, dict[str, int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        h, a = self.meta.home.team_id, self.meta.away.team_id
        self.state = MatchState(match_id=self.meta.match_id, seq=0, period=1, t_ms=0,
                                home=TeamStats(team=h), away=TeamStats(team=a))
        for t in (self.meta.home, self.meta.away):
            for p in t.players:
                self.state.players[p.player_id] = PlayerStats(player_id=p.player_id, team=t.team_id)
        self._poss_ms = {h: 0, a: 0}
        self._players = {p.player_id: (p, t) for t in (self.meta.home, self.meta.away) for p in t.players}

    def _team(self, team_id: str) -> TeamStats:
        return self.state.home if team_id == self.state.home.team else self.state.away

    def _sign(self, team_id: str) -> float:
        return 1.0 if team_id == self.state.home.team else -1.0

    def apply(self, ev: MatchEvent) -> list[Moment]:
        if ev.type == EventType.CROWD:  # feeds the strike cue only; not part of match state
            self.crowd_level = float(ev.attrs.get("level", self.crowd_level))
            return []
        s = self.state
        if ev.period != s.period:
            self._last_t = 0
        s.period, s.t_ms, s.seq, s.last_event_id = ev.period, ev.t_ms, ev.seq, ev.event_id
        s.minute = ev.minute if ev.minute is not None else ev.t_ms // 60000 + (45 if ev.period == 2 else 0)
        if ev.x is not None:
            s.zone = zone(ev.x, ev.y)
        if ev.stoppage_id:
            self._stoppages.setdefault(ev.stoppage_id, []).append(ev)
        self._track_phase(ev)
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
                self._focus(ev.player).passes_completed = ps.passes_completed
                if ps.passes_completed == 50:
                    s.milestones.append(Milestone(subject=ev.player or "", kind="passes_completed", value=50,
                                                  event_id=ev.event_id))
            self._recent.append((ev.t_ms, ev.team, 0.15 if ev.attrs.get("progressive") else 0.05))
        elif ev.type == EventType.CARRY and ps:
            ps.distance_m += ev.attrs.get("distance_m", 0)
            spd = ev.attrs.get("speed_kmh", 0)
            focus = self._focus(ev.player)
            if spd >= SPRINT_KMH:
                focus.sprints += 1
            if spd > ps.top_speed_kmh:
                ps.top_speed_kmh = focus.top_speed_kmh = spd
                if spd >= SPEED_THRESHOLD_KMH:
                    moments.append(self._moment(ev, MomentKind.SPEED_THRESHOLD, 0.35,
                                                f"{self._name(ev.player)} hits {spd} km/h"))
        elif ev.type == EventType.SHOT_TAKEN and ev.team:
            moments.append(self._moment(ev, MomentKind.SHOT, 0.25, f"{self._name(ev.player)} shoots",
                                        beat="strike", snapshot=self._strike_snapshot(ev)))
        elif ev.type == EventType.SHOT and ts and ps:
            xg = float(ev.attrs.get("xg", 0))
            ts.shots += 1
            ps.shots += 1
            ts.xg = round(ts.xg + xg, 3)
            ps.xg = round(ps.xg + xg, 3)
            self._focus(ev.player).xg = ps.xg
            if ev.outcome in ("goal", "saved"):
                ts.shots_on_target += 1
            self._recent.append((ev.t_ms, ev.team, 0.5 + xg))
            self._shots.append((ev.period, ev.t_ms, ev.team or "", xg, ev.event_id))
            rank = self._ledger_add(ev, xg)
            self._update_windows(ev)
            if ev.outcome == "goal":
                ts.goals += 1
                ps.goals += 1
                if ts.goals == 1:
                    s.milestones.append(Milestone(subject=ev.team or "", kind="first_goal", value=1,
                                                  event_id=ev.event_id))
                self._recap(ev, "goal", "GOAL {player} ({body}, xG {xg})")
                moments.append(self._moment(ev, MomentKind.GOAL, 1.0,
                                            f"GOAL {self._name(ev.player)} ({ev.attrs.get('body')}, xG {xg})",
                                            snapshot=self._goal_snapshot(ev, xg)))
            elif xg >= BIG_CHANCE_XG:
                self._recap(ev, "big_chance", "Big chance {player} {outcome} (xG {xg})")
                moments.append(self._moment(ev, MomentKind.BIG_CHANCE, 0.6 + xg / 3,
                                            f"Big chance {self._name(ev.player)} {ev.outcome} (xG {xg})",
                                            beat="result", snapshot=self._chance_snapshot(ev, xg, rank)))
        elif ev.type == EventType.PRESSURE and ts and ps:
            ts.pressures += 1
            ps.pressures += 1
            if (ev.x or 0) > 50:
                self._high_press.append((ev.period, ev.t_ms, ev.team or ""))
            m = ev.t_ms // 60000 + (45 if ev.period == 2 else 0)
            self._pressure_min[m] = self._pressure_min.get(m, 0) + 1
            if self._pressure_min[m] == PRESSURE_SPIKE_PER_MIN:
                moments.append(self._moment(ev, MomentKind.PRESSURE_SPIKE, 0.5,
                                            f"{self._tname(ev.team)} pressing hard: {PRESSURE_SPIKE_PER_MIN} pressures in a minute"))
        elif ev.type == EventType.TACKLE and ps:
            ps.tackles += 1
            self._recent.append((ev.t_ms, ev.team, 0.1))
        elif ev.type == EventType.STOPPAGE:
            s.last_stoppage = StoppageSummary(stoppage_id=ev.stoppage_id or ev.event_id, reason=ev.attrs["reason"],
                                              against=ev.attrs.get("against"), restart=ev.attrs.get("restart"))
            snap = self._stoppage_snapshot(ev)
            moments.append(self._moment(ev, MomentKind.STOPPAGE, stoppage_importance(snap), self._stoppage_line(ev),
                                        snapshot=snap))
        elif ev.type == EventType.CARD:
            color = ev.attrs.get("color", "yellow")
            counts = self._cards.setdefault(ev.player or "", {"yellow": 0, "red": 0})
            counts["red" if color in ("red", "second_yellow") else "yellow"] += 1
            if s.last_stoppage and s.last_stoppage.stoppage_id == ev.stoppage_id:
                s.last_stoppage.card = color
            kind = MomentKind.RED_CARD if color in ("red", "second_yellow") else MomentKind.CARD
            label = {"yellow": "Yellow card", "second_yellow": "Second yellow, sent off", "red": "Red card"}[color]
            self._recap(ev, "card", label + " {player}")
            moments.append(self._moment(ev, kind, 0.7 if kind == MomentKind.RED_CARD else 0.45,
                                        f"{label} {self._name(ev.player)}", snapshot=self._card_snapshot(ev, color)))
        elif ev.type == EventType.HALF_END:
            moments.append(self._moment(ev, MomentKind.HALF_END, 0.8, "Half time", snapshot=self._period_snapshot(ev)))
        elif ev.type == EventType.MATCH_END:
            moments.append(self._moment(ev, MomentKind.MATCH_END, 1.0, "Full time", snapshot=self._period_snapshot(ev)))

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
        s.momentum_label = momentum_label(s.momentum)  # type: ignore[assignment]
        if ev.type != EventType.SHOT:
            self._update_windows(ev)
        # ppda per team (passes allowed per defensive action)
        for me, them in ((s.home, s.away), (s.away, s.home)):
            da = me.pressures * 0.25 + sum(p.tackles for p in s.players.values() if p.team == me.team)
            me.ppda = round(them.passes / da, 1) if da else None
        # milestones
        if ps and ps.passes in (50, 100) and ev.type == EventType.PASS:
            moments.append(self._moment(ev, MomentKind.MILESTONE, 0.3, f"{self._name(ev.player)} reaches {ps.passes} passes"))
        return moments

    # ---------- derived state ----------
    def _focus(self, pid: str | None) -> PlayerFocus:
        return self.state.player_focus.setdefault(pid or "", PlayerFocus())

    def _track_phase(self, ev: MatchEvent) -> None:
        if not ev.phase_id:
            return
        ph = self.state.phase
        if ph is None or ph.phase_id != ev.phase_id:
            ph = self.state.phase = PhaseSummary(phase_id=ev.phase_id, team=ev.team or "", started_zone=zone(ev.x, ev.y),
                                                 started_minute=self.state.minute)
            self._phase_events = []
        self._phase_events.append(ev)
        if ev.type == EventType.PASS and ev.outcome == "success":
            ph.passes += 1
        if ev.player and ev.player not in ph.players:
            ph.players.append(ev.player)

    def _ledger_add(self, ev: MatchEvent, xg: float) -> int:
        led = self.state.shot_ledger
        led.append(ShotLedgerEntry(event_id=ev.event_id, minute=self.state.minute or 0, team=ev.team or "",
                                   player=ev.player or "", xg=xg, outcome=ev.outcome, zone=zone(ev.x, ev.y) or "",
                                   chance_rank=0))
        led.sort(key=lambda e: (-e.xg, e.minute))
        for i, e in enumerate(led, start=1):
            e.chance_rank = i
        return next(e.chance_rank for e in led if e.event_id == ev.event_id)

    def _update_windows(self, ev: MatchEvent) -> None:
        """Trailing 5-minute xG and shots per team; pressure trend value and its slope (last half vs first half)."""
        now, half = ev.t_ms, WINDOW_MS // 2
        for team in (self.state.home.team, self.state.away.team):
            shots = [(t, xg) for p, t, tm, xg, _ in self._shots if p == ev.period and tm == team and now - WINDOW_MS < t <= now]
            press = [t for p, t, tm in self._high_press if p == ev.period and tm == team and now - WINDOW_MS < t <= now]
            late = sum(xg for t, xg in shots if t > now - half) + 0.01 * sum(t > now - half for t in press)
            early = sum(xg for t, xg in shots if t <= now - half) + 0.01 * sum(t <= now - half for t in press)
            xg5 = round(sum(xg for _, xg in shots), 3)
            self.state.windows[team] = TeamWindow(xg_5m=xg5, shots_5m=len(shots))
            self.state.pressure_trend[team] = PressureTrend(value=round(xg5 + 0.01 * len(press), 3),
                                                            slope=round(late - early, 3))

    def _recap(self, ev: MatchEvent, kind: str, template: str) -> None:
        self.state.recap_points.append(RecapPoint(minute=self.state.minute or 0, kind=kind, text_template=template,
                                                  cites=[ev.event_id]))

    # ---------- snapshots: the only thing agents see; every cite resolves inside ----------
    @staticmethod
    def _ev(ev: MatchEvent) -> dict[str, Any]:
        return ev.model_dump(mode="json", exclude_none=True,
                             include={"event_id", "type", "team", "player", "x", "y", "outcome", "minute", "second",
                                      "phase_id", "stoppage_id", "attrs"})

    def _who(self, pid: str | None) -> dict[str, Any] | None:
        if not pid or pid not in self._players:
            return None
        p, t = self._players[pid]
        return {"player_id": p.player_id, "name": p.name, "number": p.number, "team": t.team_id}

    def _score_clock(self, ev: MatchEvent) -> dict[str, Any]:
        s = self.state
        return {"score": {s.home.team: s.home.goals, s.away.team: s.away.goals},
                "clock": {"period": ev.period, "minute": s.minute, "second": ev.second if ev.second is not None
                          else (ev.t_ms // 1000) % 60}}

    def _trend(self, team: str) -> dict[str, Any]:
        w, tr = self.state.windows.get(team), self.state.pressure_trend.get(team)
        return {"team": team, "xg_5m": w.xg_5m if w else 0.0, "shots_5m": w.shots_5m if w else 0,
                "pressure_slope": tr.slope if tr else 0.0, "momentum_label": self.state.momentum_label}

    def _strike_snapshot(self, ev: MatchEvent) -> dict[str, Any]:
        return {"event": self._ev(ev), "shooter": self._who(ev.player), "crowd_level": self.crowd_level,
                **self._score_clock(ev)}

    def _chance_snapshot(self, ev: MatchEvent, xg: float, rank: int) -> dict[str, Any]:
        team = ev.team or ""
        history = [{"event_id": eid, "minute": None, "xg": x, "outcome": None}
                   for p, t, tm, x, eid in self._shots if p == ev.period and tm == team and ev.t_ms - WINDOW_MS < t <= ev.t_ms]
        by_id = {e.event_id: e for e in self.state.shot_ledger}
        for h in history:
            led = by_id[h["event_id"]]
            h["minute"], h["outcome"] = led.minute, led.outcome
        return {"shot": self._ev(ev), "shooter": self._who(ev.player), "keeper": self._who(ev.attrs.get("keeper")),
                "xg": xg, "chance_quality": chance_quality(xg), "zone": zone(ev.x, ev.y), "shot_history": history,
                "chance_rank": rank, "trend": self._trend(team),
                "hold_advice": hold_advice(self.state, team, self._tname(team)).model_dump(), **self._score_clock(ev)}

    def _goal_snapshot(self, ev: MatchEvent, xg: float) -> dict[str, Any]:
        team = ev.team or ""
        phase = [e for e in self._phase_events if e.phase_id == ev.phase_id]
        prior = [e for e in phase if e.type == EventType.SHOT and e.event_id != ev.event_id]
        key = next((e for e in reversed(phase) if e.type == EventType.PASS and e.attrs.get("key_pass")), None)
        how = ("penalty" if ev.attrs.get("set_piece") == "penalty"
               else f"rebound after {self._name(prior[-1].player)}'s {prior[-1].outcome} shot" if prior
               else f"from a {ev.attrs['set_piece'].replace('_', ' ')}" if ev.attrs.get("set_piece") not in (None, "none")
               else "open play")
        return {"goal": self._ev(ev), "scorer": self._who(ev.player), "how": how,
                "body_part": ev.attrs.get("body_part"), "assist_by": self._who(ev.attrs.get("assist_by")),
                "key_pass": self._ev(key) if key else None,
                "build_up": self.state.phase.model_dump() if self.state.phase else None,
                "xg": xg, "chance_quality": chance_quality(xg), "zone": zone(ev.x, ev.y),
                "trend_before": self._trend(team),
                "time_remaining_min": max(0, 90 - (self.state.minute or 0)), **self._score_clock(ev)}

    def _stoppage_line(self, ev: MatchEvent) -> str:
        linked = self._stoppages.get(ev.stoppage_id or "", [])
        foul = next((e for e in linked if e.type == EventType.FOUL), None)
        reason, restart = ev.attrs["reason"], (ev.attrs.get("restart") or "").replace("_", " ")
        if foul:
            return f"Foul by {self._name(foul.player)} on {self._name(foul.attrs.get('fouled'))}; {restart}"
        if reason == "offside":
            return f"Offside against {self._name(ev.player)}; {restart}"
        return f"Play stopped ({reason}); {restart}"

    def _stoppage_snapshot(self, ev: MatchEvent) -> dict[str, Any]:
        linked = self._stoppages.get(ev.stoppage_id or "", [])
        foul = next((e for e in linked if e.type == EventType.FOUL), None)
        against = ev.attrs.get("against")
        restart_team = (self.state.away.team if against == self.state.home.team else self.state.home.team) if against else None
        snap: dict[str, Any] = {
            "stoppage": self._ev(ev), "reason": ev.attrs["reason"], "against": against,
            "restart": {"type": ev.attrs.get("restart"), "team": restart_team,
                        "zone": zone(100 - ev.x, 100 - ev.y) if ev.x is not None and ev.y is not None else None},
            **self._score_clock(ev)}
        if foul:
            snap.update(foul=self._ev(foul), offender=self._who(foul.player), fouled=self._who(foul.attrs.get("fouled")))
        if ev.attrs["reason"] == "offside":
            snap["offside_player"] = self._who(ev.player)
        return snap

    def _card_snapshot(self, ev: MatchEvent, color: str) -> dict[str, Any]:
        stop = next((e for e in self._stoppages.get(ev.stoppage_id or "", []) if e.type == EventType.STOPPAGE), None)
        snap = self._stoppage_snapshot(stop) if stop else self._score_clock(ev)
        snap.update(card=self._ev(ev), color=color, player=self._who(ev.player),
                    card_history=self._cards.get(ev.player or "", {}), sent_off=color != "yellow")
        return snap

    def _period_snapshot(self, ev: MatchEvent) -> dict[str, Any]:
        s = self.state
        return {"event": self._ev(ev), "recap_points": [r.model_dump() for r in s.recap_points],
                "top_chances": [e.model_dump() for e in s.shot_ledger[:3]],
                "stats": {t.team: {"goals": t.goals, "shots": t.shots, "xg": t.xg, "possession_pct": t.possession_pct}
                          for t in (s.home, s.away)}, **self._score_clock(ev)}

    # ---------- moments ----------
    def _moment(self, ev: MatchEvent, kind: MomentKind, importance: float, summary: str, beat: str = "single",
                snapshot: dict[str, Any] | None = None) -> Moment:
        self._moment_n += 1
        return Moment(moment_id=f"{self.meta.match_id}-mo{self._moment_n:04d}", match_id=self.meta.match_id,
                      t_ms=ev.t_ms, period=ev.period, kind=kind, importance=round(min(1.0, importance), 2),
                      team=ev.team, player=ev.player, event_ids=[ev.event_id], summary=summary,
                      state=self.state.model_copy(deep=True), beat=beat, trigger_event_id=ev.event_id,  # type: ignore[arg-type]
                      phase_id=ev.phase_id, stoppage_id=ev.stoppage_id, priority=PRIORITY.get(kind, 0),
                      snapshot=snapshot or {})

    def _name(self, pid: str | None) -> str:
        return self._players[pid][0].name if pid in self._players else (pid or "?")

    def _tname(self, tid: str | None) -> str:
        return self.meta.home.name if tid == self.meta.home.team_id else self.meta.away.name

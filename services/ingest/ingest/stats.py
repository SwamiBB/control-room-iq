"""Fold MatchEvents into MatchState and detect Moments.

Pure functions, no I/O: the same code runs in unit tests, in the Event Hubs consumer, and in the
API's local replay mode. Everything here is deterministic ground truth that the agents are later
evaluated against.

v0.2 state (docs/CHANGES-2026-10-23.md): the shot ledger with chance ranks, 5-minute xG and shot windows,
pressure trend, momentum label, last stoppage, current phase and recap points. A big chance is two moments:
`beat="chance"` on the strike (shot_taken, so the fan cue can air at once) and `beat="result"` on the shot.

Match intelligence (docs/HANDOFF-2026-10-24-match-intelligence.md): pass quality (distance, the passer's accuracy,
difficulty and its label, ball speed), shot speed, sprints, threshold crossings, `standout_pass` moments, and
`Moment.metrics` with the numbers that belong to each moment. Running distance comes from the tracking stream when
the match has one (carry-only distance is far too low to quote). The rules and thresholds are in derive.py.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from crq_schemas import (
    EventType,
    MatchEvent,
    MatchMeta,
    MatchState,
    Moment,
    MomentKind,
    MomentMetrics,
    PassQuality,
    PhaseSummary,
    PlayerStats,
    RecapPoint,
    ShotRecord,
    StoppageInfo,
    TeamStats,
    ThresholdIndicator,
)

from .derive import (
    BIG_CHANCE_XG,
    DISTANCE_KM,
    HARD_PASS,
    KEEP_PER_KIND,
    MIN_DISTANCE_M,
    PASS_DIFFICULTY,
    PASS_DISTANCE_M,
    SHOT_SPEED_KMH,
    SPRINT_KMH,
    TOP_SPEED_KMH,
    TREND_MS,
    WINDOW_MS,
    difficulty_label,
    distance_to_goal,
    momentum_label,
    pressure_trend,
    stoppage_importance,
    threshold_label,
    zone,
)
from .tracking_distance import TrackingDistances, find_tracking

SPEED_THRESHOLD_KMH = TOP_SPEED_KMH  # the old name, kept for anything importing it
STANDOUT_GAP_MS = 5 * 60 * 1000  # at most one standout_pass moment per team in this much play
MOMENTUM_SHIFT_DELTA = 0.6
PRESSURE_SPIKE_PER_MIN = 9
RECAP_MIN_IMPORTANCE = 0.6
PHASE_EVENTS = (EventType.PASS, EventType.CARRY, EventType.SHOT_TAKEN, EventType.SHOT)


def _keep_latest_per_kind(crossings: list[ThresholdIndicator]) -> list[ThresholdIndicator]:
    """The newest KEEP_PER_KIND crossings of each kind, in time order (newest last)."""
    seen: dict[str, int] = {}
    kept = []
    for t in reversed(crossings):
        seen[t.kind] = seen.get(t.kind, 0) + 1
        if seen[t.kind] <= KEEP_PER_KIND:
            kept.append(t)
    return kept[::-1]


@dataclass
class StateFolder:
    meta: MatchMeta
    state: MatchState = field(init=False)
    crowd_level: float = 0.0
    _poss_ms: dict[str, int] = field(default_factory=dict)
    _last_poss_team: str | None = None
    _last_t: int = 0
    _recent: deque = field(default_factory=lambda: deque(maxlen=60))  # (play_ms, team, weight)
    _pressure_min: dict[int, int] = field(default_factory=dict)
    _moment_n: int = 0
    _p1_end: int = 0
    _high_press: list[tuple[int, str]] = field(default_factory=list)  # (play_ms, team) in the opponent's half
    tracking: TrackingDistances | None = None  # found automatically for reference matches; see tracking_distance.py
    use_tracking: bool = True
    _crossed: list[ThresholdIndicator] = field(default_factory=list)  # crossed on the event being applied
    _strike_speed: ThresholdIndicator | None = None  # shot speed crossed at the strike; its result shows it, uncounted
    _player_passes: dict[str, list[float]] = field(default_factory=dict)  # player -> [passes, metres, difficulty]
    _team_passes: dict[str, list[float]] = field(default_factory=dict)  # team -> [passes, metres, difficulty]
    _pass_to: dict[str, tuple[PassQuality, str | None]] = field(default_factory=dict)  # receiver -> (pass, phase_id)
    _distance_marks: dict[str, set[float]] = field(default_factory=dict)
    _standout_at: dict[str, int] = field(default_factory=dict)  # team -> play_ms of its last standout_pass

    def __post_init__(self) -> None:
        h, a = self.meta.home.team_id, self.meta.away.team_id
        self.state = MatchState(match_id=self.meta.match_id, seq=0, period=1, t_ms=0,
                                home=TeamStats(team=h), away=TeamStats(team=a))
        for t in (self.meta.home, self.meta.away):
            for p in t.players:
                self.state.players[p.player_id] = PlayerStats(player_id=p.player_id, team=t.team_id)
        self._poss_ms = {h: 0, a: 0}
        if self.tracking is None and self.use_tracking:
            self.tracking = find_tracking(self.meta.match_id, self.meta.seed)

    def _team(self, team_id: str) -> TeamStats:
        return self.state.home if team_id == self.state.home.team else self.state.away

    def _sign(self, team_id: str) -> float:
        return 1.0 if team_id == self.state.home.team else -1.0

    def _play_ms(self, ev: MatchEvent) -> int:
        """Files written before v0.2 carry no play_ms: lay the periods end to end."""
        if ev.play_ms:
            return ev.play_ms
        return ev.t_ms if ev.period == 1 else self._p1_end + ev.t_ms

    def apply(self, ev: MatchEvent) -> list[Moment]:
        s = self.state
        if ev.type == EventType.CROWD:  # feeds the fan cue's level; not part of match state
            self.crowd_level = float(ev.attrs.get("crowd_level", self.crowd_level))
            return []
        if ev.period != s.period:
            self._last_t = 0
        s.period, s.t_ms, s.seq, s.last_event_id = ev.period, ev.t_ms, ev.seq, ev.event_id
        s.play_ms = self._play_ms(ev)
        self._crossed = []
        self._update_distances()
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
        self._track_phase(ev)

        ps = s.players.get(ev.player) if ev.player else None
        ts = self._team(ev.team) if ev.team else None

        if ev.type == EventType.PASS and ts and ps:
            ts.passes += 1
            ps.passes += 1
            ok = ev.outcome == "success"
            if ok:
                ts.passes_completed += 1
                ps.passes_completed += 1
            if ev.attrs.get("key_pass"):
                ps.key_passes += 1
            self._recent.append((ev.play_ms, ev.team, 0.15 if ev.attrs.get("progressive") else 0.05))
            moments += self._rate_pass(ev, ps, ts, ok)
        elif ev.type == EventType.CARRY and ps:
            if self.tracking is None:  # without tracking only runs with the ball count (too low to quote)
                ps.distance_m += ev.attrs.get("distance_m", 0)
            spd = ev.attrs.get("speed_kmh", 0)
            if spd >= SPRINT_KMH:
                ps.sprints += 1
            if spd > ps.top_speed_kmh:
                ps.top_speed_kmh = spd
                if spd >= SPEED_THRESHOLD_KMH:
                    self._cross("top_speed", ev, ev.player, ev.team, spd, SPEED_THRESHOLD_KMH, "km/h")
                    moments.append(self._moment(ev, MomentKind.SPEED_THRESHOLD, 0.35,
                                                f"{self._name(ev.player)} hits {spd:g} km/h"))
        elif ev.type == EventType.SHOT_TAKEN and ev.team:
            xg = float(ev.attrs.get("xg") or 0)
            speed = ev.attrs.get("speed_kmh")
            self._strike_speed = None
            if xg >= BIG_CHANCE_XG:  # the chance beat: the strike, before anyone knows the outcome
                if speed and speed >= SHOT_SPEED_KMH:  # the badge goes out with the strike, not a second later (#43)
                    self._strike_speed = self._cross("shot_speed", ev, ev.player, ev.team, speed, SHOT_SPEED_KMH,
                                                     "km/h")
                moments.append(self._moment(ev, MomentKind.BIG_CHANCE, 0.6 + xg / 3,
                                            f"{self._name(ev.player)} shoots, a big chance (xG {xg})", beat="chance"))
        elif ev.type == EventType.SHOT and ts and ps:
            xg = float(ev.attrs.get("xg", 0))
            ts.shots += 1
            ps.shots += 1
            ts.xg = round(ts.xg + xg, 3)
            ps.xg = round(ps.xg + xg, 3)
            if ev.outcome in ("goal", "saved"):
                ts.shots_on_target += 1
            self._recent.append((ev.play_ms, ev.team, 0.5 + xg))
            speed = ev.attrs.get("speed_kmh")
            if speed:
                ps.max_shot_speed_kmh = max(ps.max_shot_speed_kmh, speed)
                ts.max_shot_speed_kmh = max(ts.max_shot_speed_kmh, speed)
            strike, self._strike_speed = self._strike_speed, None
            if strike is not None and strike.player != ev.player:
                strike = None
            if strike is not None:  # crossed at the strike: the result card shows it too, but it isn't counted again
                self._crossed.append(strike)
            elif speed and speed >= SHOT_SPEED_KMH:
                self._cross("shot_speed", ev, ev.player, ev.team, speed, SHOT_SPEED_KMH, "km/h")
            self._ledger_add(ev, xg)
            self._update_windows()
            if s.current_phase and s.current_phase.phase_id == ev.phase_id:
                s.current_phase.ended_with = "shot"
            if ev.outcome == "goal":
                ts.goals += 1
                ps.goals += 1
                assister = s.players.get(ev.attrs.get("assist_by") or "")
                if assister:
                    assister.assists += 1
                moments.append(self._moment(ev, MomentKind.GOAL, 1.0,
                                            f"GOAL {self._name(ev.player)} ({ev.attrs.get('body')}, xG {xg})",
                                            beat="result"))
            elif xg >= BIG_CHANCE_XG:
                moments.append(self._moment(ev, MomentKind.BIG_CHANCE, 0.6 + xg / 3,
                                            f"Big chance {self._name(ev.player)} {ev.outcome} (xG {xg})",
                                            beat="result"))
        elif ev.type == EventType.PRESSURE and ts and ps:
            ts.pressures += 1
            ps.pressures += 1
            if (ev.x or 0) > 50:
                self._high_press.append((s.play_ms, ev.team or ""))
            m = ev.t_ms // 60000 + (45 if ev.period == 2 else 0)
            self._pressure_min[m] = self._pressure_min.get(m, 0) + 1
            if self._pressure_min[m] == PRESSURE_SPIKE_PER_MIN:
                summary = f"{self._tname(ev.team)} pressing hard: {PRESSURE_SPIKE_PER_MIN} pressures in a minute"
                moments.append(self._moment(ev, MomentKind.PRESSURE_SPIKE, 0.5, summary))
        elif ev.type == EventType.TACKLE and ps:
            ps.tackles += 1
            self._recent.append((ev.play_ms, ev.team, 0.1))
        elif ev.type == EventType.POSSESSION_CHANGE:
            if s.current_phase and s.current_phase.team != ev.team and not s.current_phase.ended_with:
                s.current_phase.ended_with = "turnover"
        elif ev.type == EventType.STOPPAGE:
            moments += self._stoppage(ev)
        elif ev.type == EventType.CARD:
            card = ev.attrs.get("card") or ev.attrs.get("color") or "yellow"
            label = {"yellow": "Yellow card", "second_yellow": "Second yellow, sent off", "red": "Red card"}.get(
                card, "Yellow card")
            moments.append(self._moment(ev, MomentKind.CARD, 0.45 if card == "yellow" else 0.7,
                                        f"{label} {self._name(ev.player)}"))
        elif ev.type == EventType.SUBSTITUTION:
            off, on = ev.attrs.get("off"), ev.attrs.get("on") or ev.player
            moments.append(self._moment(ev, MomentKind.SUBSTITUTION, 0.2,
                                        f"{self._name(on)} on for {self._name(off)}"))
        elif ev.type == EventType.HALF_END:
            self._p1_end = ev.t_ms
            moments.append(self._moment(ev, MomentKind.HALF_END, 0.8, "Half time"))
        elif ev.type == EventType.MATCH_END:
            moments.append(self._moment(ev, MomentKind.MATCH_END, 1.0, "Full time"))

        # momentum: weighted recent actions, decayed over the last ~3 minutes of play time (the period clock
        # restarts at half time, so it would give first-half actions a negative age)
        now = ev.play_ms
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
            self._update_windows()
        # ppda per team (passes allowed per defensive action)
        for me, them in ((s.home, s.away), (s.away, s.home)):
            da = me.pressures * 0.25 + sum(p.tackles for p in s.players.values() if p.team == me.team)
            me.ppda = round(them.passes / da, 1) if da else None
        # milestones
        if ps and ps.passes in (50, 100) and ev.type == EventType.PASS:
            summary = f"{self._name(ev.player)} reaches {ps.passes} passes"
            moments.append(self._moment(ev, MomentKind.MILESTONE, 0.3, summary))
        for m in moments:  # what a viewer who just joined is told (GET /recap)
            if m.importance >= RECAP_MIN_IMPORTANCE and m.beat != "chance":
                s.recap_points.append(RecapPoint(play_ms=m.play_ms, period=m.period, t_ms=m.t_ms, kind=m.kind.value,
                                                 importance=m.importance, summary=m.summary,
                                                 event_ids=list(m.event_ids)))
        return moments

    # ---------- match intelligence ----------
    def _cross(self, kind: str, ev: MatchEvent | None, player: str | None, team: str | None, value: float,
               threshold: float, unit: str) -> ThresholdIndicator:
        """Record a threshold crossing on the state (newest last) and on the event being applied."""
        t = ThresholdIndicator(kind=kind, player=player, team=team, event_id=ev.event_id if ev else None,  # type: ignore[arg-type]
                               play_ms=self.state.play_ms, value=round(value, 2), threshold=threshold, unit=unit,  # type: ignore[arg-type]
                               label=threshold_label(round(value, 2), threshold, unit))
        self.state.thresholds = _keep_latest_per_kind([*self.state.thresholds, t])
        if ev is not None:
            self._crossed.append(t)
        return t

    def _update_distances(self) -> None:
        """Running totals from tracking, and the 5 / 10 km marks. No tracking: carries only, no marks."""
        if self.tracking is None:
            return
        for pid, metres in self.tracking.advance(self.state.play_ms).items():
            ps = self.state.players.get(pid)
            if ps is None:
                continue
            ps.distance_m = round(metres, 1)
            marks = self._distance_marks.setdefault(pid, set())
            for km in DISTANCE_KM:
                if metres >= km * 1000 and km not in marks:
                    marks.add(km)
                    self._cross("distance", None, pid, ps.team, metres / 1000, km, "km")

    def _rate_pass(self, ev: MatchEvent, ps: PlayerStats, ts: TeamStats, ok: bool) -> list[Moment]:
        """Pass quality: averages for player and team, the passer's accuracy, last_pass, thresholds, standouts."""
        a = ev.attrs
        ts.pass_accuracy_pct = round(100 * ts.passes_completed / ts.passes, 1)  # every pass, with a distance or not
        if a.get("distance_m") is None:
            return []
        dist, diff = float(a["distance_m"]), min(1.0, float(a.get("difficulty") or 0.0))
        for sums, key, stats in ((self._player_passes, ev.player or "", ps), (self._team_passes, ev.team or "", ts)):
            n, metres, rating = sums.setdefault(key, [0, 0.0, 0.0])
            sums[key] = [n + 1, metres + dist, rating + diff]
            stats.avg_pass_difficulty = round((rating + diff) / (n + 1), 3)
            if stats is ps:
                ps.avg_pass_distance_m = round((metres + dist) / (n + 1), 1)
        if ok and diff >= HARD_PASS:
            ps.hard_passes_completed += 1
        pq = PassQuality(event_id=ev.event_id, play_ms=self.state.play_ms, team=ev.team or "", player=ev.player or "",
                         receiver=a.get("receiver"), distance_m=round(dist, 1), difficulty=round(diff, 2),
                         difficulty_label=difficulty_label(diff),  # type: ignore[arg-type]
                         accuracy_pct=round(100 * ps.passes_completed / ps.passes, 1),
                         ball_speed_kmh=a.get("ball_speed_kmh"), completed=ok, progressive=bool(a.get("progressive")),
                         key_pass=bool(a.get("key_pass")))
        self.state.last_pass = pq
        if not ok:
            return []
        if pq.receiver:
            self._pass_to[pq.receiver] = (pq, ev.phase_id)
        if diff >= PASS_DIFFICULTY:
            self._cross("pass_difficulty", ev, ev.player, ev.team, diff, PASS_DIFFICULTY, "rating")
        if dist >= PASS_DISTANCE_M:
            self._cross("pass_distance", ev, ev.player, ev.team, dist, PASS_DISTANCE_M, "m")
        # A standout pass is a very hard pass that sets up a shot: 2-5 a match on the reference matches. Very hard
        # alone fires 15 times a match (the simulator rates most forward passes into the final third that high).
        last = self._standout_at.get(pq.team)
        if not (diff >= PASS_DIFFICULTY and pq.key_pass) or (
                last is not None and self.state.play_ms - last < STANDOUT_GAP_MS):
            return []
        self._standout_at[pq.team] = self.state.play_ms
        return [self._moment(ev, MomentKind.STANDOUT_PASS, 0.4,
                             f"{self._name(ev.player)} picks out {self._name(pq.receiver)} with a very hard pass "
                             f"({dist:g} m, difficulty {diff:.2f})")]

    def _metrics(self, ev: MatchEvent, kind: MomentKind) -> MomentMetrics | None:
        """The numbers that belong to this moment; None when there are none."""
        ps = self.state.players.get(ev.player or "")
        m = MomentMetrics(player=ev.player, thresholds=list(self._crossed))
        if ps is not None and kind in (MomentKind.SPEED_THRESHOLD, MomentKind.BIG_CHANCE, MomentKind.GOAL,
                                       MomentKind.STANDOUT_PASS):
            if kind == MomentKind.SPEED_THRESHOLD:
                m.player_speed_kmh = ev.attrs.get("speed_kmh")
            m.player_top_speed_kmh = ps.top_speed_kmh or None
            if self.tracking is not None and ps.distance_m >= MIN_DISTANCE_M:  # carry-only totals are never quoted
                m.player_distance_km = round(ps.distance_m / 1000, 2)
            m.player_sprints = ps.sprints or None
        if kind in (MomentKind.BIG_CHANCE, MomentKind.GOAL):
            sent = self._pass_to.get(ev.player or "")
            if sent and sent[1] == ev.phase_id:  # the pass that set this chance up, in the same move
                m.key_pass = sent[0]
            m.shot_speed_kmh = ev.attrs.get("speed_kmh")  # on the strike too, so the live chance overlay has it
            if None not in (ev.x, ev.y, ev.end_x, ev.end_y):  # the strike alone has no end yet: no path
                m.shot_path = [(ev.x, ev.y), (ev.end_x, ev.end_y)]
        if kind == MomentKind.STANDOUT_PASS and self.state.last_pass is not None:
            m.key_pass = self.state.last_pass
            m.ball_speed_kmh = self.state.last_pass.ball_speed_kmh
        filled = any(v not in (None, []) for k, v in m.model_dump().items() if k != "player")
        return m if filled else None

    # ---------- derived state ----------
    def _track_phase(self, ev: MatchEvent) -> None:
        if not ev.phase_id or ev.type not in PHASE_EVENTS:
            return
        s = self.state
        ph = s.current_phase
        if ph is None or ph.phase_id != ev.phase_id:
            ph = s.current_phase = PhaseSummary(phase_id=ev.phase_id, team=ev.team or "", start_play_ms=s.play_ms)
        if ev.type == EventType.PASS and ev.outcome == "success":
            ph.passes += 1
            if ev.attrs.get("progressive"):
                ph.progressive_passes += 1
        if ev.player and ev.player not in ph.players:
            ph.players.append(ev.player)

    def _ledger_add(self, ev: MatchEvent, xg: float) -> None:
        shots = self.state.shots
        shots.append(ShotRecord(event_id=ev.event_id, play_ms=self.state.play_ms, period=ev.period, t_ms=ev.t_ms,
                                team=ev.team or "", player=ev.player or "", xg=xg, outcome=ev.outcome,
                                zone=zone(ev.x, ev.y), speed_kmh=ev.attrs.get("speed_kmh"), **self._shot_detail(ev)))
        for rank, rec in enumerate(sorted(shots, key=lambda r: (-r.xg, r.play_ms)), start=1):
            rec.chance_rank = rank

    def _shot_detail(self, ev: MatchEvent) -> dict:
        """What the shot event carries, plus distance to goal and how long the move took."""
        a, ph = ev.attrs, self.state.current_phase
        return {
            "x": ev.x, "y": ev.y, "end_x": ev.end_x, "end_y": ev.end_y,
            "body": a.get("body"), "keeper": a.get("keeper"), "blocker": a.get("blocker"),
            "assist_by": a.get("assist_by"), "assist_event_id": a.get("assist_event_id"),
            "distance_to_goal_m": distance_to_goal(ev.x, ev.y),
            "build_up_ms": self.state.play_ms - ph.start_play_ms if ph and ph.phase_id == ev.phase_id else None,
        }

    def _update_windows(self) -> None:
        s = self.state
        now = s.play_ms
        for ts in (s.home, s.away):
            recent = [r for r in s.shots if r.team == ts.team and now - WINDOW_MS < r.play_ms <= now]
            ts.xg_last_5min = round(sum(r.xg for r in recent), 3)
            ts.shots_last_5min = len(recent)
        # pressure trend of the side carrying the threat over the last 3 minutes
        half = TREND_MS // 2

        def threat(team: str, lo: int, hi: int) -> float:
            xg = sum(r.xg for r in s.shots if r.team == team and lo < r.play_ms <= hi)
            return xg + 0.01 * sum(1 for t, tm in self._high_press if tm == team and lo < t <= hi)

        team = max((s.home.team, s.away.team), key=lambda t: threat(t, now - TREND_MS, now))
        shots_3min = sum(1 for r in s.shots if r.team == team and now - TREND_MS < r.play_ms <= now)
        s.pressure_trend = pressure_trend(threat(team, now - half, now), threat(team, now - TREND_MS, now - half),  # type: ignore[assignment]
                                          shots_3min)

    def _stoppage(self, ev: MatchEvent) -> list[Moment]:
        s, a = self.state, ev.attrs
        reason, restart = a.get("reason", "other"), a.get("restart", "none")
        s.last_stoppage = StoppageInfo(stoppage_id=ev.stoppage_id or ev.event_id, play_ms=s.play_ms, reason=reason,
                                       against_team=a.get("against_team"), against_player=a.get("against_player"),
                                       restart=restart, restart_x=a.get("restart_x"), restart_y=a.get("restart_y"))
        if s.current_phase and not s.current_phase.ended_with:
            s.current_phase.ended_with = "foul" if reason == "foul" else "stoppage"
        if reason not in ("foul", "offside", "injury", "var_review"):
            return []  # goals, balls out and the half-time and full-time whistles have their own moments or none
        fouled_x = 100 - a["restart_x"] if a.get("restart_x") is not None else None  # restart, fouled team's frame
        who = self._name(a.get("against_player"))
        line = {"foul": f"Foul by {who}", "offside": f"Offside against {who}"}.get(reason, f"Play stopped: {reason}")
        return [self._moment(ev, MomentKind.STOPPAGE, stoppage_importance(reason, restart, fouled_x),
                             f"{line}; {restart.replace('_', ' ')}")]

    def _moment(self, ev: MatchEvent, kind: MomentKind, importance: float, summary: str,
                beat: str = "none") -> Moment:
        self._moment_n += 1
        # a badge carried from another event (a fast strike's, on its result) cites that event too
        carried = [t.event_id for t in self._crossed if t.event_id and t.event_id != ev.event_id]
        event_ids = [ev.event_id, *dict.fromkeys(carried)]
        return Moment(moment_id=f"{self.meta.match_id}-mo{self._moment_n:04d}", match_id=self.meta.match_id,
                      play_ms=self.state.play_ms, t_ms=ev.t_ms, period=ev.period, kind=kind, beat=beat,  # type: ignore[arg-type]
                      importance=round(min(1.0, importance), 2), team=ev.team, player=ev.player,
                      event_ids=event_ids, summary=summary, state=self.state.model_copy(deep=True),
                      metrics=self._metrics(ev, kind))

    def _name(self, pid: str | None) -> str:
        for t in (self.meta.home, self.meta.away):
            for p in t.players:
                if p.player_id == pid:
                    return p.name
        return pid or "?"

    def _tname(self, tid: str | None) -> str:
        return self.meta.home.name if tid == self.meta.home.team_id else self.meta.away.name

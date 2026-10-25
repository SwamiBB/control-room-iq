"""Storyline-driven generator for the reference matches.

A storyline (data/storyline*.json) pins each demo moment to a minute; between beats the seeded
possession-phase engine plays ordinary football. Differences from MatchEngine.run():

- every random draw comes from a named stream derived from the seed, so adding an event type to one
  subsystem does not move the rest of the match;
- unscripted goals are suppressed (saved instead), so the final score is the scripted one;
- shots are split into shot_taken (the strike, carrying xG) and shot (the result); fouls, offsides,
  goals, balls out and the half-time and full-time whistles become `stoppage` events linked by
  stoppage_id; possession events carry phase_id;
- a crowd level is emitted twice a second, with the event it is reacting to.

The output is a list of v0.2 MatchEvents in match-clock order, renumbered, with play_ms filled. `attrs` keys
follow the contract (packages/schemas MatchEvent docstring). Coordinates follow the existing rule: 0-100,
normalised to the acting team's attacking direction, with y > 50 on the attacking team's left.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from crq_schemas import EventType, MatchEvent, MatchMeta, Team

from .engine import MatchEngine

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
FRAME_MS = 250  # tracking tick (4 Hz); frame n is at play_ms n * FRAME_MS
CROWD_MS = 500  # crowd cadence (2 Hz)
BUILD_GAP_MS = 2200  # time between passes in a scripted build-up
POSSESSION_TYPES = {EventType.PASS, EventType.CARRY, EventType.SHOT_TAKEN, EventType.SHOT}


def stream(seed: int, name: str) -> random.Random:
    """Independent, stable RNG per subsystem. str hash() is salted per process, so use sha256."""
    digest = hashlib.sha256(f"{seed}:{name}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def load_clubs(path: Path = DATA_DIR / "clubs.json") -> dict[str, Team]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {c["team_id"]: Team.model_validate(c) for c in raw["clubs"]}


def load_storyline(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_scripted_meta(story: dict[str, Any], clubs: dict[str, Team] | None = None) -> MatchMeta:
    clubs = clubs or load_clubs()
    return MatchMeta(match_id=story["match_id"], venue=story["venue"],
                     kickoff_utc=datetime.fromisoformat(story["kickoff_utc"].replace("Z", "+00:00")),
                     home=clubs[story["home"]], away=clubs[story["away"]], seed=story["seed"])


def period_ms(period: int, minute: int, second: int = 0) -> int:
    return (minute - (45 if period == 2 else 0)) * 60000 + second * 1000


def opta_clock(period: int, t_ms: int) -> tuple[int, int]:
    """Minute counts from the match kickoff (period 2 starts at 45); first-half stoppage time is 45+."""
    return t_ms // 60000 + (45 if period == 2 else 0), (t_ms // 1000) % 60


def play_ms(period: int, t_ms: int, p1_end_ms: int) -> int:
    """Monotonic play time from the first kickoff: the second half continues where the first ended."""
    return t_ms if period == 1 else p1_end_ms + t_ms


def frame_index(period: int, t_ms: int, p1_end_ms: int) -> int:
    return play_ms(period, t_ms, p1_end_ms) // FRAME_MS


def expand_beats(beats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten pressure builds into individual shot beats and attach period-clock times."""
    out: list[dict[str, Any]] = []
    for b in beats:
        if b["kind"] == "pressure_build":
            for s in b["shots"]:
                out.append({"kind": "shot", "period": b["period"], "team": b["team"], "build_up_passes": 2, **s})
        else:
            out.append(dict(b))
    for b in out:
        b["t_ms"] = period_ms(b["period"], b["minute"], b.get("second", 0))
    return sorted(out, key=lambda b: (b["period"], b["t_ms"]))


def generate(story_path: Path, clubs: dict[str, Team] | None = None) -> tuple[MatchMeta, list[MatchEvent]]:
    story = load_storyline(story_path)
    meta = build_scripted_meta(story, clubs)
    return meta, ScriptedEngine(meta, story).run()


class ScriptedEngine(MatchEngine):
    def __init__(self, meta: MatchMeta, story: dict[str, Any]) -> None:
        super().__init__(meta)
        self.story = story
        self.rng = stream(meta.seed, "play")
        self.flight_rng = stream(meta.seed, "shot_flight")
        self.crowd_rng = stream(meta.seed, "crowd")
        self.sub_rng = stream(meta.seed, "substitutions")
        self.teams = {meta.home.team_id: meta.home, meta.away.team_id: meta.away}
        self.sent_off: set[str] = set()
        self.subbed_off: set[str] = set()
        self.came_on: set[str] = set()
        self.yellows: set[str] = set()
        self.phase_id: str | None = None
        self.phase_team: str | None = None
        self._phase_n = 0
        self._stop_n = 0
        self._subs_done: set[str] = set()
        self._pending_set_piece: str | None = None
        self._assist_of: dict[int, MatchEvent] = {}  # id(shot) -> the pass that set it up (event ids come last)
        self.block_rng = stream(meta.seed, "blockers")  # its own stream: naming a blocker moves nothing else

    def _link_assist(self, shot: MatchEvent, key_pass: MatchEvent) -> None:
        shot.attrs["assist_by"] = key_pass.player
        self._assist_of[id(shot)] = key_pass

    # ---------- helpers ----------
    def _opp(self, team: Team) -> Team:
        return self.meta.away if team.team_id == self.meta.home.team_id else self.meta.home

    def _active(self, team: Team):
        return [p for p in team.players
                if p.player_id not in self.sent_off and p.player_id not in self.subbed_off
                and (p.number <= 11 or p.player_id in self.came_on)]

    def _pick(self, team: Team, weights: dict[str, float]) -> str:
        players = [p for p in self._active(team) if p.position != "GK"]
        w = [weights.get(p.position, 1.0) for p in players]
        return self.rng.choices(players, weights=w, k=1)[0].player_id

    def _keeper(self, team: Team) -> str:
        return next(p.player_id for p in self._active(team) if p.position == "GK")

    def _mk(self, type_: EventType, t_ms: int, team: str | None = None, player: str | None = None,
            **kw: Any) -> MatchEvent:
        self.seq += 1
        return MatchEvent(event_id=f"tmp-{self.seq}", match_id=self.meta.match_id, seq=self.seq, t_ms=t_ms,
                          period=self.period, type=type_, team=team, player=player, **kw)  # type: ignore[arg-type]

    def _new_phase(self, team_id: str) -> None:
        self._phase_n += 1
        self.phase_id = f"{self.meta.match_id}-ph{self._phase_n:04d}"
        self.phase_team = team_id

    def _new_stoppage(self) -> str:
        self._stop_n += 1
        return f"{self.meta.match_id}-st{self._stop_n:04d}"

    def _tag_phase(self, evs: list[MatchEvent]) -> None:
        for e in evs:
            if e.type in POSSESSION_TYPES and e.team == self.phase_team:
                e.phase_id = self.phase_id

    def _is_quiet(self, team_id: str | None, t_ms: int) -> bool:
        minute, _ = opta_clock(self.period, t_ms)
        return any(w["period"] == self.period and w["from_minute"] <= minute < w["to_minute"] and team_id in w["teams"]
                   for w in self.story.get("quiet_windows", []))

    # ---------- shots ----------
    def _split_shot(self, shot: MatchEvent) -> list[MatchEvent]:
        """Unscripted shot -> shot_taken (the strike, carrying xG) + shot (the result, after the ball's flight)."""
        taken = self._mk(EventType.SHOT_TAKEN, shot.t_ms, shot.team, shot.player, x=shot.x, y=shot.y,
                         attrs={"xg": shot.attrs.get("xg"), "body": shot.attrs.get("body", "foot"),
                                "speed_kmh": shot.attrs.get("speed_kmh")})
        shot.t_ms += self.flight_rng.randint(400, 900)
        return [taken, shot]

    def _scripted_shot(self, team: Team, s: dict[str, Any], t: int) -> tuple[list[MatchEvent], MatchEvent]:
        opp = self._opp(team)
        x, y = float(s["x"]), float(s["y"])
        body = "header" if s.get("body_part") == "head" else "foot"
        side = s.get("direction") or ("left" if y > 55 else "right" if y < 45 else "center")
        end_y = {"left": 53.0, "right": 47.0, "center": 50.0}[side]
        speed = round(self.flight_rng.uniform(85, 115) * (0.7 if body == "header" else 1.0), 1)
        attrs: dict[str, Any] = {"xg": s["xg"], "body": body, "speed_kmh": speed, "keeper": self._keeper(opp)}
        for k in ("assist_by", "blocker", "set_piece", "counter"):
            if s.get(k) is not None:
                attrs[k] = s[k]
        taken = self._mk(EventType.SHOT_TAKEN, t, team.team_id, s["player"], x=x, y=y,
                         attrs={"xg": s["xg"], "body": body, "speed_kmh": speed})
        shot = self._mk(EventType.SHOT, t + self.flight_rng.randint(400, 900), team.team_id, s["player"], x=x, y=y,
                        end_x=100.0, end_y=end_y, outcome=s["outcome"], attrs=attrs)
        return [taken, shot], shot

    def _stoppage(self, t: int, team: str | None, reason: str, restart: str, x: float | None = None,
                  y: float | None = None, against_player: str | None = None, whistle: str | None = "stop",
                  sid: str | None = None) -> tuple[str, list[MatchEvent]]:
        """A stoppage (and the whistle that signals it), in the contract's attrs. Coordinates in `team`'s frame."""
        sid = sid or self._new_stoppage()
        out = []
        if whistle:
            out.append(self._mk(EventType.WHISTLE, t, attrs={"kind": whistle, "stoppage_id": sid}, stoppage_id=sid))
        out.append(self._mk(EventType.STOPPAGE, t + 900, team, against_player, x=x, y=y, stoppage_id=sid,
                            attrs={"reason": reason, "against_team": team, "against_player": against_player,
                                   "restart": restart, "restart_x": x, "restart_y": y}))
        return sid, out

    def _after_shot(self, team: Team, shot: MatchEvent) -> tuple[list[MatchEvent], Team, float, float]:
        opp, t = self._opp(team), shot.t_ms
        if shot.outcome == "goal":
            self.score[team.team_id] += 1
            _, stop = self._stoppage(t + 400, opp.team_id, "goal", "kickoff", 50.0, 50.0, whistle="goal")
            ko = self._mk(EventType.KICKOFF, t + self.rng.randint(45000, 60000), opp.team_id, None, x=50, y=50,
                          attrs={"after": "goal"})
            return stop + [ko], opp, 50.0, 50.0
        if shot.outcome == "saved":
            return [self._mk(EventType.POSSESSION_CHANGE, t + 2500, opp.team_id, self._keeper(opp), x=5, y=50,
                             attrs={"reason": "saved"})], opp, 8.0, 50.0
        if shot.outcome == "blocked":
            blocker = shot.attrs.get("blocker") or self._pick(opp, {"DF": 2.0})
            shot.attrs["blocker"] = blocker
            bx, by = 100 - (shot.x or 85), 100 - (shot.y or 50)
            return [self._mk(EventType.POSSESSION_CHANGE, t + 1300, opp.team_id, blocker, x=bx, y=by,
                             attrs={"reason": "blocked"})], opp, bx, by
        _, stop = self._stoppage(t + 800, team.team_id, "ball_out", "goal_kick", 6.0, 50.0, whistle=None)
        return stop + [self._mk(EventType.POSSESSION_CHANGE, t + 15000, opp.team_id, self._keeper(opp), x=6, y=50,
                                attrs={"reason": "off_target", "restart": "goal_kick"})], opp, 8.0, 50.0

    def _build_up(self, team: Team, n: int, end_x: float, end_y: float, shooter: str, assist_by: str | None,
                  t_end: int, set_piece: str | None = None) -> list[MatchEvent]:
        """n completed passes ending with the key pass to the shooter at (end_x, end_y), the last at t_end."""
        n = max(1, n)
        pool = [p.player_id for p in self._active(team)
                if p.position != "GK" and p.player_id not in (shooter, assist_by)]
        chain: list[str] = []
        for _ in range(n - 1):
            chain.append(self.rng.choice([p for p in pool if not chain or p != chain[-1]]))
        chain.append(assist_by or self.rng.choice([p for p in pool if not chain or p != chain[-1]]))
        x0, y0 = max(12.0, end_x - 10.0 * n), 50.0 + self.rng.uniform(-18, 18)
        pts = [(x0 + (end_x - x0) * k / n,
                (y0 + (end_y - y0) * k / n) + (self.rng.uniform(-12, 12) if 0 < k < n else 0))
               for k in range(n + 1)]
        evs = []
        for i, passer in enumerate(chain):
            (sx, sy), (ex, ey) = pts[i], pts[i + 1]
            sx, sy, ex, ey = (round(min(max(v, 2), 98), 1) for v in (sx, sy, ex, ey))
            dist = self._dist(sx, sy, ex, ey)
            dx = ex - sx
            attrs: dict[str, Any] = {
                "receiver": shooter if i == n - 1 else chain[i + 1], "distance_m": round(dist, 1),
                "difficulty": round(min(1.0, 0.15 + dist / 60 + (0.25 if ex > 75 else 0) + (0.2 if dx > 15 else 0)), 2),
                "progressive": dx > 10, "ball_speed_kmh": round(30 + dist * 0.9, 1), "completed": True}
            if i == n - 1:
                attrs["key_pass"] = True
            if i == 0 and set_piece:
                attrs["set_piece"] = set_piece
            evs.append(self._mk(EventType.PASS, t_end - (n - i) * BUILD_GAP_MS, team.team_id, passer,
                                x=sx, y=sy, end_x=ex, end_y=ey, outcome="success", attrs=attrs))
        return evs

    # ---------- stoppages ----------
    def _foul_sequence(self, foul: MatchEvent, card: str | None, restart: str) -> tuple[list[MatchEvent], int]:
        """foul -> whistle -> stoppage -> card -> restart whistle, all sharing one stoppage_id."""
        t = foul.t_ms
        sid, stop = self._stoppage(t + 300, foul.team, "foul", restart, foul.x, foul.y, against_player=foul.player)
        foul.stoppage_id = sid
        foul.attrs.update({"reason": "foul", "stoppage_id": sid, **({"card": card} if card else {})})
        out = [foul, *stop]
        if card:
            if card in ("red", "second_yellow"):
                self.sent_off.add(foul.player or "")
            else:
                self.yellows.add(foul.player or "")
            out.append(self._mk(EventType.CARD, t + 25000, foul.team, foul.player, stoppage_id=sid,
                                attrs={"card": card, "reason": "foul", "stoppage_id": sid}))
        restart_t = t + (35000 if card else self.rng.randint(12000, 18000))
        out.append(self._mk(EventType.WHISTLE, restart_t, attrs={"kind": "restart", "stoppage_id": sid},
                            stoppage_id=sid))
        return out, restart_t

    # ---------- unscripted play ----------
    def _unscripted_phase(self, team: Team, opp: Team, x: float, y: float):
        self._new_phase(team.team_id)
        set_piece, self._pending_set_piece = self._pending_set_piece, None
        nxt, nx, ny, raw = self._run_phase(team, opp, x, y)
        out: list[MatchEvent] = []
        drop_kickoff = relabel_next = False
        for e in raw:
            if e.type == EventType.SHOT:
                if e.outcome == "goal":  # reference matches end on the scripted score
                    self.score[e.team or ""] -= 1
                    drop_kickoff = True
                    nx, ny = 8.0, 50.0
                if self._is_quiet(e.team, e.t_ms):  # keep scripted moments clean: the attack ends in a cut-out cross
                    out.append(self._mk(EventType.PASS, e.t_ms, e.team, e.player, x=e.x, y=e.y,
                                        end_x=min(97.0, (e.x or 85) + 8), end_y=50.0, outcome="fail",
                                        attrs={"receiver": None, "distance_m": 12.0, "difficulty": 0.85,
                                               "progressive": False, "cross": True, "ball_speed_kmh": 60.0,
                                               "completed": False}))
                    if drop_kickoff:
                        out.append(self._mk(EventType.POSSESSION_CHANGE, e.t_ms + 2500, opp.team_id,
                                            self._keeper(opp), x=5, y=50, attrs={"reason": "claimed"}))
                    else:
                        relabel_next = True
                    continue
                if e.outcome == "goal":
                    e.outcome = "saved"
                last_pass = next((p for p in reversed(out) if p.type == EventType.PASS and p.team == e.team), None)
                if last_pass and last_pass.outcome == "success" and last_pass.attrs.get("receiver") == e.player:
                    last_pass.attrs["key_pass"] = True
                    self._link_assist(e, last_pass)
                if e.outcome == "blocked" and not e.attrs.get("blocker"):  # the base engine never names one
                    defenders = [p.player_id for p in self._active(opp) if p.position in ("DF", "MF")]
                    e.attrs["blocker"] = self.block_rng.choice(defenders)
                out.extend(self._split_shot(e))
                if drop_kickoff:
                    out.append(self._mk(EventType.POSSESSION_CHANGE, e.t_ms + 2500, opp.team_id, self._keeper(opp),
                                        x=5, y=50, attrs={"reason": "saved"}))
                continue
            if e.type == EventType.KICKOFF and drop_kickoff:
                continue
            if e.type == EventType.POSSESSION_CHANGE and relabel_next:
                e.attrs["reason"] = "interception"
                relabel_next = False
            if e.type == EventType.CARD:
                continue  # rebuilt inside the foul sequence
            if e.type == EventType.FOUL:
                card = e.attrs.pop("card", None)
                if card and (e.player in self.yellows or self._is_quiet(e.team, e.t_ms)):
                    card = None  # no unscripted second yellows, no cards inside quiet windows
                if (e.x or 50) < 17 and 21 < (e.y or 50) < 79:
                    e.x = 18.0  # unscripted fouls stay outside the box: no unscripted penalties
                holder = next((p for p in reversed(out) if p.team != e.team and p.player
                               and p.type in (EventType.PASS, EventType.CARRY)), None)
                if holder:  # the fouled player is whoever had the ball
                    e.attrs["fouled"] = (holder.attrs.get("receiver") if holder.type == EventType.PASS
                                         and holder.outcome == "success" else holder.player)
                seq, restart_t = self._foul_sequence(e, card, "free_kick")
                out.extend(seq)
                self.t_ms = max(self.t_ms, restart_t + 2000)
                self._pending_set_piece = "free_kick"
                continue
            if e.type == EventType.PASS:
                e.attrs["completed"] = e.outcome == "success"
                if set_piece:
                    e.attrs["set_piece"], set_piece = set_piece, None
            out.append(e)
        self._tag_phase(out)
        return nxt, nx, ny, out

    def _maybe_substitute(self, out: list[MatchEvent]) -> None:
        if self.period != 2 or self.t_ms < 16 * 60000:
            return
        for team in (self.meta.home, self.meta.away):
            if team.team_id in self._subs_done:
                continue
            bench = [p for p in team.players
                     if p.number > 11 and p.position != "GK" and p.player_id not in self.came_on]
            starters = [p for p in self._active(team) if p.number <= 11 and p.position != "GK"]
            if bench and starters:
                on, off = bench[0], self.sub_rng.choice(starters)
                out.append(self._mk(EventType.SUBSTITUTION, self.t_ms, team.team_id, on.player_id,
                                    attrs={"off": off.player_id, "on": on.player_id}))
                self.came_on.add(on.player_id)
                self.subbed_off.add(off.player_id)
            self._subs_done.add(team.team_id)

    # ---------- scripted beats ----------
    @staticmethod
    def _lead_ms(b: dict[str, Any]) -> int:
        if b["kind"] in ("shot", "goal", "chance_then_rebound_goal"):
            return max(1, b.get("build_up_passes", 3)) * BUILD_GAP_MS
        return 0

    def _beat(self, b: dict[str, Any]) -> tuple[list[MatchEvent], Team, float, float]:
        kind, t = b["kind"], b["t_ms"]
        team = self.teams[b["team"]]
        if kind in ("shot", "goal"):
            s = {**b, "outcome": "goal"} if kind == "goal" else b
            self._new_phase(team.team_id)
            sp = b.get("set_piece") if b.get("set_piece") not in (None, "none", "penalty") else None
            evs = self._build_up(team, b.get("build_up_passes", 3), b["x"], b["y"], b["player"], b.get("assist_by"),
                                 t, sp)
            shot_evs, shot = self._scripted_shot(team, s, t)
            self._link_assist(shot, evs[-1])
            tail, nxt, nx, ny = self._after_shot(team, shot)
            evs += shot_evs + tail
            self._tag_phase(evs)
            return evs, nxt, nx, ny
        if kind == "chance_then_rebound_goal":
            c, r = b["chance"], b["rebound"]
            self._new_phase(team.team_id)
            evs = self._build_up(team, b.get("build_up_passes", 5), c["x"], c["y"], c["player"], c.get("assist_by"), t)
            first, saved = self._scripted_shot(team, c, t)
            self._link_assist(saved, evs[-1])
            second, goal = self._scripted_shot(team, r, saved.t_ms + r["after_ms"])
            tail, nxt, nx, ny = self._after_shot(team, goal)
            evs += first + second + tail
            self._tag_phase(evs)
            return evs, nxt, nx, ny
        if kind in ("foul", "red_card"):
            fouled_team = self._opp(team)
            foul = self._mk(EventType.FOUL, t, team.team_id, b["player"], x=100 - b["x"], y=100 - b["y"],
                            attrs={"fouled": b["fouled"]})
            evs, restart_t = self._foul_sequence(foul, b.get("card"), b.get("restart", "free_kick"))
            self.t_ms = restart_t + 1000
            self._pending_set_piece = b.get("restart", "free_kick")
            return evs, fouled_team, float(b["x"]), float(b["y"])
        if kind == "penalty_goal":
            defending, f = self._opp(team), b["foul"]
            foul = self._mk(EventType.FOUL, t, defending.team_id, f["player"], x=100 - f["x"], y=100 - f["y"],
                            attrs={"fouled": f["fouled"], "in_box": True})
            evs, _ = self._foul_sequence(foul, f.get("card"), "penalty")
            p = {**b["penalty"], "x": 88.5, "y": 50.0, "set_piece": "penalty"}
            self._new_phase(team.team_id)
            shot_evs, shot = self._scripted_shot(team, p, t + p["after_ms"])
            tail, nxt, nx, ny = self._after_shot(team, shot)
            self._tag_phase(shot_evs)
            return evs + shot_evs + tail, nxt, nx, ny
        if kind == "offside":
            defending = self._opp(team)
            x, y = float(b["x"]), float(b["y"])
            self._new_phase(team.team_id)
            restart = b.get("restart", "free_kick")
            sid, stop = self._stoppage(t + 600, team.team_id, "offside", restart, x, y, against_player=b["player"])
            dist = self._dist(x - 18, y + 5, x, y)
            pass_ = self._mk(EventType.PASS, t, team.team_id, b["passer"], x=x - 18, y=y + 5, end_x=x, end_y=y,
                             outcome="fail", stoppage_id=sid,
                             attrs={"receiver": b["player"], "offside": True, "distance_m": round(dist, 1),
                                    "difficulty": 0.5, "progressive": True, "completed": False,
                                    "ball_speed_kmh": round(30 + dist * 0.9, 1)})
            self._tag_phase([pass_])
            evs = [pass_, *stop, self._mk(EventType.WHISTLE, t + 12000, attrs={"kind": "restart", "stoppage_id": sid},
                                          stoppage_id=sid)]
            self.t_ms = t + 14000
            self._pending_set_piece = b.get("restart", "free_kick")
            return evs, defending, 100 - x, 100 - y
        raise ValueError(f"unknown beat kind: {kind}")

    def _period_end(self, b: dict[str, Any]) -> list[MatchEvent]:
        t, end = b["t_ms"], b["kind"]
        _, stop = self._stoppage(t, None, end, "kickoff" if end == "half_end" else "none", whistle=end)
        return stop + [self._mk(EventType.HALF_END if end == "half_end" else EventType.MATCH_END, t + 1000,
                                attrs={"score": dict(self.score)})]

    # ---------- crowd ----------
    def _crowd(self, events: list[MatchEvent]) -> list[MatchEvent]:
        """Crowd level 0-1 at 2 Hz: a baseline plus impulses that decay over about 7 s. While an impulse is still
        felt, `trigger_event_id` names the event the crowd is reacting to (filled in once ids are final)."""
        home = self.meta.home.team_id
        out: list[MatchEvent] = []
        self._crowd_trigger: dict[int, MatchEvent] = {}
        for period in (1, 2):
            self.period = period
            imps = []
            for i, e in enumerate(events):
                if e.period != period:
                    continue
                if e.type == EventType.SHOT_TAKEN:
                    imps.append((e.t_ms, i, 0.35 if e.team == home else 0.2))
                elif e.type == EventType.SHOT and e.outcome == "goal":
                    imps.append((e.t_ms, i, 0.55 if e.team == home else 0.3))
                elif e.type == EventType.CARD:
                    imps.append((e.t_ms, i, 0.2))
                elif e.type in (EventType.STOPPAGE, EventType.KICKOFF):
                    imps.append((e.t_ms, i, 0.08))
            imps.sort()
            end = max(e.t_ms for e in events if e.period == period)
            excite = drift = 0.0
            trigger: MatchEvent | None = None
            j = 0
            for t in range(0, end + 1, CROWD_MS):
                excite *= math.exp(-CROWD_MS / 7000)
                while j < len(imps) and imps[j][0] <= t:
                    excite += imps[j][2]
                    trigger = events[imps[j][1]]
                    j += 1
                if excite < 0.05:
                    trigger = None
                drift = 0.9 * drift + self.crowd_rng.gauss(0, 0.01)
                level = min(1.0, max(0.0, 0.35 + excite + drift))
                c = self._mk(EventType.CROWD, t, attrs={"crowd_level": round(level, 2), "trigger_event_id": None})
                if trigger is not None:
                    self._crowd_trigger[id(c)] = trigger
                out.append(c)
        return out

    # ---------- public ----------
    def run(self) -> list[MatchEvent]:  # type: ignore[override]
        beats = expand_beats(self.story["beats"])
        events: list[MatchEvent] = []
        for period in (1, 2):
            self.period, self.t_ms = period, 0
            team = self.meta.home if period == 1 else self.meta.away
            events.append(self._mk(EventType.KICKOFF, 0, team.team_id, None, x=50, y=50, attrs={"period": period}))
            last_t, self.t_ms = 0, 1000
            x, y = 50.0, 50.0
            for b in (b for b in beats if b["period"] == period):
                start = b["t_ms"] - self._lead_ms(b)
                if last_t >= start:
                    raise ValueError(f"beat {b.get('id')} starts before the previous beat has finished")
                while self.t_ms < start - 3000:
                    if self.t_ms < start - 8000:
                        self._maybe_substitute(events)
                    team, x, y, evs = self._unscripted_phase(team, self._opp(team), x, y)
                    kept = [e for e in evs if e.t_ms < start - 1000]
                    events += kept
                    last_t = max([last_t] + [e.t_ms for e in kept])
                    if len(kept) < len(evs):
                        break
                self.t_ms = start
                if b["kind"] in ("half_end", "match_end"):
                    events += self._period_end(b)
                    break
                evs, team, x, y = self._beat(b)
                events += evs
                last_t = max(e.t_ms for e in evs)
                self.t_ms = max(self.t_ms, last_t + 3000)
        return self._finalise(events)

    def _finalise(self, events: list[MatchEvent]) -> list[MatchEvent]:
        crowd = self._crowd(events)
        rows = [(e.period, e.t_ms, 0, i, e) for i, e in enumerate(events)]
        rows += [(c.period, c.t_ms, 1, i, c) for i, c in enumerate(crowd)]
        rows.sort(key=lambda r: r[:4])
        p1_end = next(e.t_ms for e in events if e.type == EventType.HALF_END)
        out = []
        for n, row in enumerate(rows, start=1):
            e = row[4]
            e.seq, e.event_id = n, f"{self.meta.match_id}-{n:05d}"
            e.play_ms = play_ms(e.period, e.t_ms, p1_end)
            out.append(e)
        for e in events:  # ids are final now
            key_pass = self._assist_of.get(id(e))
            if key_pass is not None:
                e.attrs["assist_event_id"] = key_pass.event_id
        for c in crowd:
            trigger = self._crowd_trigger.get(id(c))
            if trigger is not None:
                c.attrs["trigger_event_id"] = trigger.event_id
        return out

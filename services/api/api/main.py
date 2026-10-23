"""Control Room IQ API: operator console, approval loop, overlay feed, viewer feeds.

Local mode (default): `uvicorn api.main:app --reload` then POST /matches/replay with a match file to
run the full pipeline in-process (simulator -> stats -> agents -> proposals -> approvals -> overlay).
Azure mode: ingest/agents run as separate Container Apps; this service consumes `crq-moments` and
publishes approved items to `crq-overlay`. Both modes share the same in-memory hub below, which is
swapped for Cosmos DB persistence via `store.py`.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from agents.config import settings as agent_settings
from agents.workflow import MomentPipeline
from crq_schemas import Decision as DecisionRecord
from crq_schemas import (DecisionLogEntry, EvaluationRecord, MatchEvent, MatchMeta, Moment, MomentKind, OverlayItem,
                         OverlayProposal, Persona, ProposalStatus, StrikeCue)
from ingest.cues import strike_cue
from ingest.stats import StateFolder
from simulator.replay import FeedItem, ReplayDriver, build_schedule

from . import evaluation, gate
from .scheduler import LayerScheduler, clock_of, match_ms

DATA = Path(__file__).resolve().parents[3] / "data"

app = FastAPI(title="Control Room IQ API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class Hub:
    """In-memory state + fan-out. Replace with Cosmos + Event Hubs in Azure mode (store.py)."""

    def __init__(self) -> None:
        self.proposals: dict[str, OverlayProposal] = {}
        self.decisions: list[DecisionLogEntry] = []
        self.results: dict[str, dict] = {}  # moment_id -> explanation/line/variants
        self.operators: set[WebSocket] = set()
        self.viewers: dict[WebSocket, dict] = {}
        self.state: dict | None = None
        self.meta: MatchMeta | None = None
        self.auto_hold_s = 20.0
        self.scheduler: LayerScheduler | None = None
        self.clock_ms = 0  # current match clock (scheduler time), advanced by the replay
        self.decision_log: list[DecisionRecord] = []  # one row per state transition (the audit trail)
        self.proposal_moment: dict[str, dict] = {}  # proposal_id -> {phase_id, stoppage_id, priority}
        self.evaluations: list[EvaluationRecord] = []  # one row per agent output (EvaluationRecorder)

    async def broadcast_screen(self) -> None:
        if self.scheduler:
            await self.broadcast_operators({"type": "screen",
                                            "screen": self.scheduler.screen(self.clock_ms).model_dump(mode="json")})

    async def broadcast_operators(self, msg: dict) -> None:
        for ws in list(self.operators):
            try:
                await ws.send_json(msg)
            except Exception:  # noqa: BLE001
                self.operators.discard(ws)

    async def broadcast_cue(self, cue: StrikeCue) -> None:
        """Strike cue to every viewer at once: no persona or language, no model, no operator gate."""
        msg = {"type": "cue", "cue": cue.model_dump(mode="json")}
        for ws in list(self.viewers):
            try:
                await ws.send_json(msg)
            except Exception:  # noqa: BLE001
                self.viewers.pop(ws, None)
        await self.broadcast_operators(msg)

    async def broadcast_viewers(self, item: OverlayItem, variants: list[dict]) -> None:
        for ws, prefs in list(self.viewers.items()):
            v = next((x for x in variants if x["persona"] == prefs["persona"] and x["lang"] == prefs["lang"]), None)
            payload = item.model_dump()
            if v:
                payload["line"], payload["persona"], payload["lang"] = v["text"], v["persona"], v["lang"]
            try:
                await ws.send_json({"type": "overlay", "item": payload})
            except Exception:  # noqa: BLE001
                self.viewers.pop(ws, None)


hub = Hub()
pipeline = MomentPipeline()


# ---------- approval loop ----------

class Decision(BaseModel):
    """Request body for operator actions. `actor` is the operator's name."""

    actor: str = "operator"
    override_line: str | None = None
    reasoning: str | None = None


async def _decide(proposal_id: str, action: str, actor: str, operator: str | None = None,
                  edited_line: str | None = None, reasoning: str | None = None) -> OverlayProposal:
    """Every state change goes through here: the gate checks it, then exactly one Decision row is written."""
    p = hub.proposals.get(proposal_id)
    if not p:
        raise HTTPException(404, "proposal not found")
    try:
        status = gate.next_status(p.status, action, actor)
    except gate.IllegalTransition as ex:
        raise HTTPException(409, str(ex)) from ex
    p.status, p.decided_by, p.decided_at = status, operator or actor, datetime.now(timezone.utc)
    if edited_line:
        p.override_line = edited_line
    hub.decision_log.append(DecisionRecord(
        decision_id=f"{p.match_id}-d{len(hub.decision_log) + 1:04d}", match_id=p.match_id, proposal_id=p.proposal_id,
        action=action, actor=actor, operator=operator, at=p.decided_at, match_clock=clock_of(hub.clock_ms),  # type: ignore[arg-type]
        edited_line=edited_line, routed_model=p.provenance.routed_model if p.provenance else None))
    hub.decisions.append(DecisionLogEntry(entry_id="d-" + uuid.uuid4().hex[:8], match_id=p.match_id, proposal_id=p.proposal_id,
                                          action=status, actor=operator or actor, at=p.decided_at, reasoning=reasoning))
    await hub.broadcast_operators({"type": "proposal", "proposal": p.model_dump(mode="json")})
    await hub.broadcast_operators({"type": "decision", "decision": hub.decision_log[-1].model_dump(mode="json")})
    evaluation.attach_decision(hub.evaluations, p.moment_id, hub.decision_log[-1].decision_id, edited_line)
    if hub.scheduler:
        if status in gate.AIRS:
            slot = hub.scheduler.approve(p.proposal_id, hub.clock_ms)
            if slot:
                p.t_start_ms, p.t_end_ms = slot.start, slot.end
        elif status in (ProposalStatus.HELD, ProposalStatus.SLA_HELD):
            hub.scheduler.hold(p.proposal_id)
        else:
            hub.scheduler.release(p.proposal_id)
        await hub.broadcast_screen()
    if status in gate.AIRS:  # the only path to the overlay feed
        item = OverlayItem(item_id="o-" + uuid.uuid4().hex[:8], match_id=p.match_id, layer=p.layer, t_start_ms=p.t_start_ms,
                           t_end_ms=p.t_end_ms, line=p.override_line or p.line, payload=p.payload, source_proposal_id=p.proposal_id)
        variants = hub.results.get(p.moment_id, {}).get("variants", [])
        await hub.broadcast_viewers(item, variants)
        p.status = ProposalStatus.AIRED
    return p


@app.post("/proposals/{proposal_id}/approve", response_model=OverlayProposal)
async def approve(proposal_id: str, d: Decision = Decision()):
    return await _decide(proposal_id, "approve", "operator", operator=d.actor, reasoning=d.reasoning)


@app.post("/proposals/{proposal_id}/hold", response_model=OverlayProposal)
async def hold(proposal_id: str, d: Decision = Decision()):
    return await _decide(proposal_id, "hold", "operator", operator=d.actor, reasoning=d.reasoning)


@app.post("/proposals/{proposal_id}/override", response_model=OverlayProposal)
async def override(proposal_id: str, d: Decision):
    if not d.override_line:
        raise HTTPException(422, "override_line required")
    return await _decide(proposal_id, "override", "operator", operator=d.actor, edited_line=d.override_line,
                         reasoning=d.reasoning)


@app.get("/api/decisions")
async def decision_log():
    """Every proposal state transition: operator actions, SLA holds and supersessions."""
    return hub.decision_log


@app.get("/api/evaluations")
async def evaluations():
    """One row per agent output: snapshot, output, cites, source, routed model, latency, operator decision."""
    return hub.evaluations


@app.get("/api/evaluations.jsonl")
async def evaluations_jsonl():
    """The same rows as query / context / response JSONL for the Foundry evaluation run."""
    return PlainTextResponse(evaluation.to_foundry_jsonl(hub.evaluations), media_type="application/jsonl",
                             headers={"Content-Disposition": 'attachment; filename="evaluations.jsonl"'})


@app.get("/api/decisions.csv")
async def decision_log_csv():
    return PlainTextResponse(gate.to_csv(hub.decision_log), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="decisions.csv"'})


async def _supersede(new_pid: str, phase_id: str | None, stoppage_id: str | None, priority: int) -> None:
    """A higher-priority moment on the same phase or stoppage replaces pending lower-priority proposals."""
    for pid, meta in list(hub.proposal_moment.items()):
        p = hub.proposals.get(pid)
        same = (phase_id and meta["phase_id"] == phase_id) or (stoppage_id and meta["stoppage_id"] == stoppage_id)
        if (pid != new_pid and p and same and meta["priority"] < priority
                and p.status in (ProposalStatus.PROPOSED, ProposalStatus.HELD, ProposalStatus.SLA_HELD)):
            await _decide(pid, "supersede", "supersession", reasoning=f"superseded by {new_pid}")


@app.get("/proposals")
async def list_proposals(status: ProposalStatus | None = None):
    return [p for p in hub.proposals.values() if status is None or p.status == status]


@app.get("/decisions")
async def decisions():
    return hub.decisions


@app.get("/state")
async def state():
    return hub.state


@app.get("/healthz")
async def healthz():
    return {"ok": True}


async def _auto_hold(proposal_id: str) -> None:
    """Approval SLA: a proposal nobody acts on is held, never aired. In Azure this is a Logic App."""
    await asyncio.sleep(hub.auto_hold_s)
    p = hub.proposals.get(proposal_id)
    if p and p.status == ProposalStatus.PROPOSED:  # any operator action before this cancels the hold
        await _decide(proposal_id, "sla_hold", "sla", reasoning=f"no operator action in {hub.auto_hold_s:g} s")


# ---------- local replay (full pipeline in-process) ----------

class ReplayRequest(BaseModel):
    file: str = "data/reference_match.jsonl"  # python -m simulator.cli reference
    speed: float = 20.0
    min_importance: float = 0.3


@app.post("/matches/replay")
async def replay(req: ReplayRequest):
    path = Path(req.file)
    if not path.exists():
        raise HTTPException(404, f"{path} not found; run the simulator first")
    asyncio.create_task(_replay(path, req.speed, req.min_importance))
    return {"started": True}


async def _replay(path: Path, speed: float, min_importance: float) -> None:
    with path.open(encoding="utf-8") as f:
        meta = MatchMeta.model_validate_json(f.readline())
        hub.meta, folder = meta, StateFolder(meta)
        await hub.broadcast_operators({"type": "match", "meta": meta.model_dump(mode="json")})
        last_t, last_p = 0, 1
        for line in f:
            if not line.strip():
                continue
            ev = MatchEvent.model_validate_json(line)
            if ev.period != last_p:
                last_t, last_p = 0, ev.period
            await asyncio.sleep(max(0.0, (ev.t_ms - last_t) / 1000 / speed))
            last_t = ev.t_ms
            moments = folder.apply(ev)
            if ev.seq % 10 == 0:
                hub.state = folder.state.model_dump(mode="json")
                await hub.broadcast_operators({"type": "state", "state": hub.state})
            for m in moments:
                if m.importance < min_importance:
                    continue
                res = await pipeline.process(m)
                hub.results[m.moment_id] = {"explanation": res.explanation.model_dump(), "line": res.line,
                                            "variants": [v.model_dump(mode="json") for v in res.variants],
                                            "failures": res.failures}
                await hub.broadcast_operators({"type": "moment", "moment": m.model_dump(mode="json", exclude={"state"}),
                                               **hub.results[m.moment_id]})
                if res.proposal:
                    hub.proposals[res.proposal.proposal_id] = res.proposal
                    await hub.broadcast_operators({"type": "proposal", "proposal": res.proposal.model_dump(mode="json")})
                    asyncio.create_task(_auto_hold(res.proposal.proposal_id))


# ---------- replay driver: the demo control, the judges' play button, the operator session's tool ----------

class ReplaySession:
    def __init__(self, meta: MatchMeta, events: list[MatchEvent], speed: float) -> None:
        self.meta, self.events = meta, events
        self.folder = StateFolder(meta)
        self.driver = ReplayDriver(build_schedule(events, meta.seed), speed=speed, on_seek=self.seek)
        self.task: asyncio.Task | None = None
        self.min_importance = 0.3

    def seek(self, index: int) -> None:
        """A jump: fold everything before the target silently (no agents), so state is right when play resumes."""
        self.folder = StateFolder(self.meta)
        for ev in self.events[:index]:
            self.folder.apply(ev)
        hub.state = self.folder.state.model_dump(mode="json")
        if index:
            hub.clock_ms = match_ms(self.events[index - 1].period, self.events[index - 1].t_ms)

    async def sink(self, item: FeedItem) -> None:
        ev = item.event
        hub.clock_ms = match_ms(ev.period, ev.t_ms)
        moments = self.folder.apply(ev)
        if ev.type.value != "crowd":
            await hub.broadcast_operators({"type": "feed", **item.envelope()})
            if ev.seq % 10 == 0:
                hub.state = self.folder.state.model_dump(mode="json")
                await hub.broadcast_operators({"type": "state", "state": hub.state})
        for m in moments:
            cue = strike_cue(m)
            if cue:  # beat one: sent inside the same feed step as the strike, no model in between
                await hub.broadcast_cue(cue)
            if m.importance >= self.min_importance:
                asyncio.create_task(_process_moment(m))  # never stall the feed on a model call


replay_session: ReplaySession | None = None


async def _process_moment(m: Moment) -> None:
    on_air = None
    if hub.scheduler:  # the Producer sees what is on screen and queued
        sc = hub.scheduler.screen(hub.clock_ms)
        on_air = [i.model_dump(mode="json") for i in sc.on_air + sc.queued]
    t0 = time.monotonic()
    res = await pipeline.process(m, on_air=on_air)
    hub.evaluations += evaluation.records_for(m, res, int((time.monotonic() - t0) * 1000), agent_settings.offline)
    hub.results[m.moment_id] = {"explanation": res.explanation.model_dump(), "line": res.line,
                                "variants": [v.model_dump(mode="json") for v in res.variants], "failures": res.failures}
    await hub.broadcast_operators({"type": "moment", "moment": m.model_dump(mode="json", exclude={"state"}),
                                   **hub.results[m.moment_id]})
    if res.proposal and hub.scheduler:  # slot on the match clock before the operator sees it
        p = res.proposal.model_copy(update={"t_start_ms": match_ms(m.period, res.proposal.t_start_ms),
                                            "t_end_ms": match_ms(m.period, res.proposal.t_end_ms)})
        res.proposal = hub.scheduler.schedule(p, match_ms(m.period, m.t_ms),
                                              preempts=m.kind in (MomentKind.GOAL, MomentKind.RED_CARD))
        await hub.broadcast_screen()
    if res.proposal:
        pid = res.proposal.proposal_id
        hub.proposals[pid] = res.proposal
        hub.proposal_moment[pid] = {"phase_id": m.phase_id, "stoppage_id": m.stoppage_id, "priority": m.priority}
        await hub.broadcast_operators({"type": "proposal", "proposal": res.proposal.model_dump(mode="json")})
        await _supersede(pid, m.phase_id, m.stoppage_id, m.priority)
        asyncio.create_task(_auto_hold(pid))


def _reference_file(seed: int) -> Path:
    for story in sorted(DATA.glob("storyline*.json")):
        if json.loads(story.read_text(encoding="utf-8"))["seed"] == seed:
            return DATA / f"reference_match{story.stem.removeprefix('storyline')}.jsonl"
    raise HTTPException(404, f"no reference match for seed {seed}")


def _session() -> ReplaySession:
    if replay_session is None:
        raise HTTPException(409, "no replay running; start one with GET /api/replay")
    return replay_session


@app.get("/api/replay")
async def start_replay(seed: int = 42, speed: float = 1.0):
    """Start (or restart) a reference match on a clock: 42 reference, 7 red card, 101 comeback."""
    global replay_session
    path = _reference_file(seed)
    if not path.exists():
        raise HTTPException(404, f"{path.name} not found; run python -m simulator.cli reference")
    if replay_session and replay_session.task:
        replay_session.task.cancel()
    lines = path.read_text(encoding="utf-8").splitlines()
    meta = MatchMeta.model_validate_json(lines[0])
    replay_session = ReplaySession(meta, [MatchEvent.model_validate_json(x) for x in lines[1:] if x.strip()], speed)
    hub.meta, hub.scheduler, hub.clock_ms = meta, LayerScheduler(meta.match_id), 0
    hub.decision_log, hub.proposal_moment = [], {}  # one audit log per replay run
    hub.proposals, hub.results, hub.evaluations = {}, {}, []  # a new match starts with an empty queue
    await hub.broadcast_operators({"type": "match", "meta": meta.model_dump(mode="json")})
    replay_session.task = asyncio.create_task(replay_session.driver.run(replay_session.sink))
    return replay_session.driver.status()


@app.post("/api/replay/pause")
async def pause_replay():
    _session().driver.pause()
    return _session().driver.status()


@app.post("/api/replay/resume")
async def resume_replay():
    _session().driver.resume()
    return _session().driver.status()


@app.post("/api/replay/speed")
async def speed_replay(x: float):
    try:
        _session().driver.set_speed(x)
    except ValueError as ex:
        raise HTTPException(422, str(ex)) from ex
    return _session().driver.status()


@app.post("/api/replay/jump")
async def jump_replay(minute: int, period: int | None = None, second: int = 0):
    """Jump to a match minute (Opta clock); period defaults from the minute (>= 45 means second half)."""
    period = period or (2 if minute >= 46 else 1)
    _session().driver.jump(period, minute, second)
    return _session().driver.status()


@app.get("/api/replay/status")
async def replay_status():
    return _session().driver.status()


@app.get("/api/screen")
async def screen():
    """ScreenState: what is on air, queued and held right now (written only by the layer scheduler)."""
    if not hub.scheduler:
        raise HTTPException(409, "no replay running; start one with GET /api/replay")
    return hub.scheduler.screen(hub.clock_ms)


# ---------- websockets ----------

@app.websocket("/ws/operator")
async def ws_operator(ws: WebSocket):
    await ws.accept()
    hub.operators.add(ws)
    try:
        if hub.meta:
            await ws.send_json({"type": "match", "meta": hub.meta.model_dump(mode="json")})
        for p in hub.proposals.values():
            await ws.send_json({"type": "proposal", "proposal": p.model_dump(mode="json")})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.operators.discard(ws)


@app.websocket("/ws/viewer")
async def ws_viewer(ws: WebSocket, persona: Persona = Persona.FAN, lang: str = "en", club: str | None = None):
    await ws.accept()
    hub.viewers[ws] = {"persona": persona.value, "lang": lang, "club": club}
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.viewers.pop(ws, None)

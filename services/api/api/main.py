"""Control Room IQ API: operator console, approval loop, overlay feed, viewer feeds.

Local mode (default): `uvicorn api.main:app --reload` then POST /matches/replay with a match file to
run the full pipeline in-process (simulator -> stats -> agents -> proposals -> approvals -> overlay).
Azure mode: ingest/agents run as separate Container Apps; this service consumes `crq-moments` and
publishes approved items to `crq-overlay`. Both modes share the same in-memory hub below, which is
swapped for Cosmos DB persistence via `store.py`.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from agents.workflow import MomentPipeline, MomentResult
from crq_schemas import (
    DecisionLogEntry,
    FanCard,
    FanCue,
    Lang,
    MatchEvent,
    MatchMeta,
    MatchState,
    Moment,
    NarrativeVariant,
    OverlayPacket,
    OverlayProposal,
    Persona,
    ProposalStatus,
    Recap,
)
from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from ingest.stats import StateFolder
from pydantic import BaseModel, Field

from .clock import PlayClock
from .exports import decisions_to_csv
from .fan_cue import build_fan_cue
from .feed import OverlayFeed, eventhubs_sink_from_env
from .packets import ViewerPrefs, attach_fan_card, build_packet, for_viewer
from .recap import RECAP_WINDOWS, build_recap
from .schedule import ScheduleView, build_schedule


@asynccontextmanager
async def lifespan(_: FastAPI):
    sink = eventhubs_sink_from_env()
    if sink:
        hub.feed.sinks.append(sink)
    yield
    if sink:
        await sink.close()


app = FastAPI(title="Control Room IQ API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class Hub:
    """In-memory state + fan-out. Replace with Cosmos + Event Hubs in Azure mode (store.py)."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.now: Callable[[], datetime] = lambda: datetime.now(UTC)
        self.proposals: dict[str, OverlayProposal] = {}
        self.decisions: list[DecisionLogEntry] = []
        self.results: dict[str, dict] = {}  # moment_id -> explanation/line/variants/fan_card
        self.packets: list[OverlayPacket] = []  # canonical packets as aired, before per-viewer variants
        self.operators: set[WebSocket] = set()
        self.viewers: dict[WebSocket, ViewerPrefs] = {}
        self.state: dict | None = None
        self.meta: MatchMeta | None = None
        self.match_state: MatchState | None = None  # live object folded by the replay
        self.clock = PlayClock()
        self.feed = OverlayFeed()
        self.auto_hold_s = 20.0

    async def broadcast_operators(self, msg: dict) -> None:
        for ws in list(self.operators):
            try:
                await ws.send_json(msg)
            except Exception:  # noqa: BLE001
                self.operators.discard(ws)

    async def broadcast_viewers(self, packet: OverlayPacket, variants: list[NarrativeVariant]) -> None:
        for ws, prefs in list(self.viewers.items()):
            item = for_viewer(packet, variants, prefs).model_dump(mode="json")
            try:
                await ws.send_json({"type": "overlay", "item": item})
            except Exception:  # noqa: BLE001
                self.viewers.pop(ws, None)

    async def broadcast_fan_cue(self, cue: FanCue) -> None:
        for ws, prefs in list(self.viewers.items()):
            if prefs.persona != Persona.DEAF:
                continue
            try:
                await ws.send_json({"type": "fan_cue", "cue": cue.model_dump(mode="json")})
            except Exception:  # noqa: BLE001
                self.viewers.pop(ws, None)


hub = Hub()
pipeline = MomentPipeline()


# ---------- approval loop ----------

SLA_ACTOR = "sla-timer"
AIRING_ACTIONS = (ProposalStatus.APPROVED, ProposalStatus.OVERRIDDEN)


class Decision(BaseModel):
    actor: str = Field(default="operator", min_length=1, max_length=64)
    override_line: str | None = Field(default=None, min_length=1, max_length=280)
    reasoning: str | None = Field(default=None, max_length=1000)


def _open_proposal(proposal_id: str, action: ProposalStatus, d: Decision) -> OverlayProposal:
    p = hub.proposals.get(proposal_id)
    if not p:
        raise HTTPException(404, "proposal not found")
    if p.status not in (ProposalStatus.PROPOSED, ProposalStatus.HELD):
        raise HTTPException(409, f"proposal already {p.status.value}")
    # No auto-approve path: the SLA timer may only hold, so its name cannot be used to air anything.
    if d.actor == SLA_ACTOR and action != ProposalStatus.HELD:
        raise HTTPException(403, f"{SLA_ACTOR} may only hold")
    return p


def _record_decision(p: OverlayProposal, action: ProposalStatus, d: Decision) -> DecisionLogEntry:
    p.status, p.decided_by, p.decided_at = action, d.actor, hub.now()
    if d.override_line:
        p.override_line = d.override_line
    entry = DecisionLogEntry(entry_id="d-" + uuid.uuid4().hex[:8], match_id=p.match_id, proposal_id=p.proposal_id,
                             action=action, actor=d.actor, at=p.decided_at, reasoning=d.reasoning)
    hub.decisions.append(entry)
    return entry


def _approved_extras(p: OverlayProposal) -> tuple[list[NarrativeVariant], FanCard | None]:
    result = hub.results.get(p.moment_id, {})
    # An override replaces the AI line for everyone, so the AI variants of it must not air.
    variants = [] if p.override_line else [NarrativeVariant.model_validate(v) for v in result.get("variants", [])]
    card = result.get("fan_card")
    return variants, FanCard.model_validate(card) if card else None


async def _air(p: OverlayProposal, approval: DecisionLogEntry) -> None:
    variants, card = _approved_extras(p)
    packet = attach_fan_card(build_packet(p, approval, hub.clock), card)
    hub.packets.append(packet)
    await hub.feed.publish("packet", packet)
    await hub.broadcast_viewers(packet, variants)
    p.status = ProposalStatus.AIRED


async def _decide(proposal_id: str, action: ProposalStatus, d: Decision) -> OverlayProposal:
    p = _open_proposal(proposal_id, action, d)
    entry = _record_decision(p, action, d)
    await hub.broadcast_operators({"type": "proposal", "proposal": p.model_dump(mode="json")})
    if action in AIRING_ACTIONS:
        await _air(p, entry)
    return p


@app.post("/proposals/{proposal_id}/approve", response_model=OverlayProposal)
async def approve(proposal_id: str, d: Decision | None = None):
    return await _decide(proposal_id, ProposalStatus.APPROVED, d or Decision())


@app.post("/proposals/{proposal_id}/hold", response_model=OverlayProposal)
async def hold(proposal_id: str, d: Decision | None = None):
    return await _decide(proposal_id, ProposalStatus.HELD, d or Decision())


@app.post("/proposals/{proposal_id}/override", response_model=OverlayProposal)
async def override(proposal_id: str, d: Decision):
    if not d.override_line:
        raise HTTPException(422, "override_line required")
    return await _decide(proposal_id, ProposalStatus.OVERRIDDEN, d)


@app.post("/proposals/{proposal_id}/reject", response_model=OverlayProposal)
async def reject(proposal_id: str, d: Decision | None = None):
    return await _decide(proposal_id, ProposalStatus.REJECTED, d or Decision())


@app.get("/decisions.csv")
async def decisions_csv():
    return Response(decisions_to_csv(hub.decisions), media_type="text/csv",
                    headers={"content-disposition": 'attachment; filename="decisions.csv"'})


@app.get("/proposals")
async def list_proposals(status: ProposalStatus | None = None):
    return [p for p in hub.proposals.values() if status is None or p.status == status]


@app.get("/decisions")
async def decisions():
    return hub.decisions


@app.get("/state")
async def state():
    return hub.state


@app.get("/schedule", response_model=ScheduleView)
async def schedule():
    return build_schedule(hub.packets, hub.proposals.values(), hub.clock)


@app.get("/recap", response_model=Recap)
async def recap(minutes: int = 10):
    # Query strings arrive as text, which Literal[10, 20, 30] will not coerce; check the window explicitly.
    if minutes not in RECAP_WINDOWS:
        raise HTTPException(422, f"minutes must be one of {RECAP_WINDOWS}")
    if hub.match_state is None:
        raise HTTPException(404, "no match in progress")
    return build_recap(hub.match_state, minutes, hub.clock.play_ms)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


async def _auto_hold(proposal_id: str) -> None:
    """Approval SLA: a proposal nobody acts on is held, never aired. In Azure this is a Logic App."""
    await asyncio.sleep(hub.auto_hold_s)
    p = hub.proposals.get(proposal_id)
    if p and p.status == ProposalStatus.PROPOSED:
        await _decide(proposal_id, ProposalStatus.HELD, Decision(actor=SLA_ACTOR, reasoning="no operator action"))


# ---------- local replay (full pipeline in-process) ----------

class ReplayRequest(BaseModel):
    file: str = "data/match.jsonl"
    speed: float = 20.0
    min_importance: float = 0.3


@app.post("/matches/replay")
async def replay(req: ReplayRequest):
    path = Path(req.file)
    if not path.exists():
        raise HTTPException(404, f"{path} not found; run the simulator first")
    asyncio.create_task(_replay(req))
    return {"started": True}


async def _replay(req: ReplayRequest) -> None:
    with Path(req.file).open(encoding="utf-8") as f:
        folder = await _start_match(MatchMeta.model_validate_json(f.readline()))
        for line in filter(str.strip, f):
            await _replay_event(folder, MatchEvent.model_validate_json(line), req)


async def _start_match(meta: MatchMeta) -> StateFolder:
    hub.meta, hub.clock = meta, PlayClock()
    await hub.broadcast_operators({"type": "match", "meta": meta.model_dump(mode="json")})
    folder = StateFolder(meta)
    hub.match_state = folder.state
    return folder


async def _replay_event(folder: StateFolder, ev: MatchEvent, req: ReplayRequest) -> None:
    # Pace on play time: the period clock restarts at half time, play time never does.
    await asyncio.sleep(hub.clock.advance(ev) / 1000 / req.speed)
    moments = folder.apply(ev)
    if ev.seq % 10 == 0:
        await _publish_state(folder)
    for m in moments:
        if m.importance >= req.min_importance:
            await _handle_moment(_stamp_play_time(m))


async def _publish_state(folder: StateFolder) -> None:
    hub.state = folder.state.model_dump(mode="json") | {"play_ms": hub.clock.play_ms}
    await hub.broadcast_operators({"type": "state", "state": hub.state, "clock": hub.clock.snapshot()})


def _stamp_play_time(m: Moment) -> Moment:
    """Ingest before v0.2 leaves Moment.play_ms at 0; the replay clock knows the real value."""
    return m if m.play_ms else m.model_copy(update={"play_ms": hub.clock.play_ms})


def _result_record(res: MomentResult) -> dict:
    # MomentResult gains `fan_card` when the workflow builds it (agents workstream); until then it is absent.
    card: FanCard | None = getattr(res, "fan_card", None)
    return {"explanation": res.explanation.model_dump(), "line": res.line,
            "variants": [v.model_dump(mode="json") for v in res.variants], "failures": res.failures,
            "fan_card": card.model_dump(mode="json") if card else None}


async def _publish_fan_cue(m: Moment) -> None:
    cue = build_fan_cue(m, home_team=m.state.home.team)
    await hub.broadcast_fan_cue(cue)
    await hub.feed.publish("fan_cue", cue)


async def _handle_moment(m: Moment) -> None:
    if m.beat == "chance":
        # The cue is code and must air within 1 s, so it goes out before any agent call (up to ~8 s each).
        await _publish_fan_cue(m)
    res = await pipeline.process(m)
    hub.results[m.moment_id] = _result_record(res)
    await hub.broadcast_operators({"type": "moment", "moment": m.model_dump(mode="json", exclude={"state"}),
                                   **hub.results[m.moment_id]})
    if res.proposal:
        await _queue_proposal(res.proposal)


async def _queue_proposal(p: OverlayProposal) -> None:
    hub.proposals[p.proposal_id] = p
    await hub.broadcast_operators({"type": "proposal", "proposal": p.model_dump(mode="json")})
    asyncio.create_task(_auto_hold(p.proposal_id))


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


@app.websocket("/ws/overlay")
async def ws_overlay(ws: WebSocket):
    """Renderer feed: every approved packet and fan cue as {type, match_id, item}."""
    await ws.accept()
    hub.feed.renderers.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.feed.renderers.discard(ws)


@app.websocket("/ws/viewer")
async def ws_viewer(ws: WebSocket, persona: Persona = Persona.FAN, lang: Lang = "en", club: str | None = None):
    await ws.accept()
    hub.viewers[ws] = ViewerPrefs(persona=persona, lang=lang, club=club)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.viewers.pop(ws, None)

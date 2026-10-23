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
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.workflow import MomentPipeline
from crq_schemas import (Access, DecisionLogEntry, MatchEvent, MatchMeta, OverlayPacket, OverlayProposal, Persona,
                         ProposalStatus)
from ingest.stats import StateFolder

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

    async def broadcast_operators(self, msg: dict) -> None:
        for ws in list(self.operators):
            try:
                await ws.send_json(msg)
            except Exception:  # noqa: BLE001
                self.operators.discard(ws)

    async def broadcast_viewers(self, item: OverlayPacket, variants: list[dict]) -> None:
        for ws, prefs in list(self.viewers.items()):
            v = next((x for x in variants if (x["persona"], x.get("access", "none"), x["lang"])
                      == (prefs["persona"], prefs["access"], prefs["lang"])), None)
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
    actor: str = "operator"
    override_line: str | None = None
    reasoning: str | None = None


async def _decide(proposal_id: str, action: ProposalStatus, d: Decision) -> OverlayProposal:
    p = hub.proposals.get(proposal_id)
    if not p:
        raise HTTPException(404, "proposal not found")
    if p.status not in (ProposalStatus.PROPOSED, ProposalStatus.HELD):
        raise HTTPException(409, f"proposal already {p.status.value}")
    p.status, p.decided_by, p.decided_at = action, d.actor, datetime.now(timezone.utc)
    if d.override_line:
        p.override_line = d.override_line
    hub.decisions.append(DecisionLogEntry(entry_id="d-" + uuid.uuid4().hex[:8], match_id=p.match_id, proposal_id=p.proposal_id,
                                          action=action, actor=d.actor, at=p.decided_at, reasoning=d.reasoning))
    await hub.broadcast_operators({"type": "proposal", "proposal": p.model_dump(mode="json")})
    if action in (ProposalStatus.APPROVED, ProposalStatus.OVERRIDDEN):
        # The gate is structural: a packet cannot exist without approval fields, so nothing generated
        # reaches a renderer unless an operator (never the SLA timer) approved or overrode it.
        entry = hub.decisions[-1]
        item = OverlayPacket(cue_id=p.cue_id or "c-" + p.proposal_id, match_id=p.match_id, layer=p.layer,
                             t_in_ms=p.t_in_ms or p.t_start_ms, t_out_ms=p.t_out_ms or p.t_end_ms,
                             period=1 if (hub.state or {}).get("period", 1) == 1 else 2,
                             clock_ms=(hub.state or {}).get("t_ms", 0), priority=p.priority, replaces=p.replaces,
                             min_hold_ms=p.min_hold_ms, line=p.override_line or p.line, payload=p.payload,
                             verified=p.faithfulness is None or p.faithfulness >= 0.8, fallback=p.fallback,
                             evidence=[e.event_id for e in p.evidence], source_proposal_id=p.proposal_id,
                             approval_id=entry.entry_id, approved_by=d.actor, approved_at=p.decided_at)
        variants = hub.results.get(p.moment_id, {}).get("variants", [])
        await hub.broadcast_viewers(item, variants)
        p.status = ProposalStatus.AIRED
    return p


@app.post("/proposals/{proposal_id}/approve", response_model=OverlayProposal)
async def approve(proposal_id: str, d: Decision = Decision()):
    return await _decide(proposal_id, ProposalStatus.APPROVED, d)


@app.post("/proposals/{proposal_id}/hold", response_model=OverlayProposal)
async def hold(proposal_id: str, d: Decision = Decision()):
    return await _decide(proposal_id, ProposalStatus.HELD, d)


@app.post("/proposals/{proposal_id}/override", response_model=OverlayProposal)
async def override(proposal_id: str, d: Decision):
    if not d.override_line:
        raise HTTPException(422, "override_line required")
    return await _decide(proposal_id, ProposalStatus.OVERRIDDEN, d)


@app.post("/proposals/{proposal_id}/reject", response_model=OverlayProposal)
async def reject(proposal_id: str, d: Decision = Decision()):
    return await _decide(proposal_id, ProposalStatus.REJECTED, d)


@app.get("/decisions.csv")
async def decisions_csv():
    from fastapi.responses import PlainTextResponse
    rows = ["entry_id,match_id,proposal_id,action,actor,at,reasoning"]
    for e in hub.decisions:
        a = e.action.value if hasattr(e.action, "value") else str(e.action)
        rows.append(f"{e.entry_id},{e.match_id},{e.proposal_id},{a},{e.actor},{e.at.isoformat()},\"{(e.reasoning or '').replace('\"', '')}\"")
    return PlainTextResponse("\n".join(rows), media_type="text/csv")


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
    if p and p.status == ProposalStatus.PROPOSED:
        await _decide(proposal_id, ProposalStatus.HELD, Decision(actor="sla-timer", reasoning="no operator action"))


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
async def ws_viewer(ws: WebSocket, persona: Persona = Persona.FAN, access: Access = "none", lang: str = "en",
                    club: str | None = None):
    await ws.accept()
    hub.viewers[ws] = {"persona": persona.value, "access": access, "lang": lang, "club": club}
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.viewers.pop(ws, None)

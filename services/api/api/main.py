"""Control Room IQ API: operator console, approval loop, overlay feed, viewer feeds.

Local mode (default): `uvicorn api.main:app --reload` then POST /matches/replay with a match file to
run the full pipeline in-process (simulator -> stats -> agents -> proposals -> approvals -> overlay).
Azure mode: ingest/agents run as separate Container Apps; this service consumes `crq-moments` and
publishes approved items to `crq-overlay`. Both modes share the same in-memory hub below, which is
swapped for Cosmos DB persistence via `store.py`.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, get_args

from agents.config import settings
from agents.workflow import MomentPipeline, MomentResult
from crq_schemas import (
    Access,
    Allegiance,
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
    ProposalStatus,
    Recap,
)
from fastapi import FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from ingest.stats import StateFolder
from pydantic import BaseModel, Field

from .clock import PlayClock
from .delivery import HIGH_STAKES_KINDS, Delivery, DeliveryPlan, apply_delivery, choose_delivery
from .exports import decisions_to_csv
from .fallback_text import template_line
from .fan_card import build_fan_card
from .fan_cue import build_fan_cue
from .feed import OverlayFeed, eventhubs_sink_from_env
from .goal_package import build_goal_package, is_code_built
from .metrics import GalleryMetrics, gallery_metrics
from .packets import ViewerPrefs, attach_fan_card, build_packet, parse_viewer, with_perspective
from .perspective import perspective
from .preview import (
    DEFAULT_VIEW,
    MAX_VIEWS,
    Preview,
    PreviewContext,
    ViewerGroup,
    parse_view,
    preview,
    view_key,
    viewer_groups,
)
from .recap import RECAP_WINDOWS, build_recap
from .schedule import ScheduleView, build_schedule
from .timing import (
    EXPIRY_ACTOR,
    SLA_ACTOR,
    SLA_HOLD_S,
    SLA_WARN_S,
    SYSTEM_ACTORS,
    shelf_life_ms,
    sla_times,
    stale_proposals,
)
from .variant_checks import build_context, unsourced_numbers


@asynccontextmanager
async def lifespan(_: FastAPI):
    sink = eventhubs_sink_from_env()
    if sink:
        hub.feed.sinks.append(sink)
    yield
    if sink:
        await sink.close()


app = FastAPI(title="Control Room IQ API", version="0.2.0", lifespan=lifespan)
logger = logging.getLogger(__name__)
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
        self.moments: dict[str, Moment] = {}  # moment_id -> moment, for variant checks and template lines
        self.deliveries: list[dict] = []  # audit: what each viewer group got for each approval, and why
        self.operators: set[WebSocket] = set()
        self.viewers: dict[WebSocket, ViewerPrefs] = {}
        self.state: dict | None = None
        self.meta: MatchMeta | None = None
        self.match_state: MatchState | None = None  # live object folded by the replay
        self.clock = PlayClock()
        self.feed = OverlayFeed()
        self.auto_hold_s = SLA_HOLD_S
        self.warn_s = SLA_WARN_S
        self.replay_speed: float | None = None  # what the match is running at, once a replay is under way
        self.replay_task: asyncio.Task | None = None

    def new_match(self, meta: MatchMeta) -> None:
        """Clear the desk for a fresh match.

        Running a second replay must not leave the first one's graphics in the log or its turnaround in
        the metrics. Connected sockets survive; everything the match produced does not.
        """
        self.meta, self.clock = meta, PlayClock()
        self.proposals.clear()
        self.decisions.clear()
        self.results.clear()
        self.packets.clear()
        self.moments.clear()
        self.deliveries.clear()
        self.state = None
        self.replay_speed = None

    async def broadcast_operators(self, msg: dict) -> None:
        for ws in list(self.operators):
            try:
                await ws.send_json(msg)
            except Exception:  # noqa: BLE001
                self.operators.discard(ws)

    async def broadcast_viewers(self, packet: OverlayPacket, plan: DeliveryPlan) -> list[dict]:
        """Sends each viewer their delivery; returns one audit entry per viewer group, not per socket."""
        chosen: dict[tuple, Delivery] = {}
        for ws, prefs in list(self.viewers.items()):
            group = (prefs.persona, prefs.access, prefs.lang)
            d = chosen.setdefault(group, choose_delivery(plan, prefs))
            framing = perspective(self.match_state, prefs, self.meta) if self.match_state else None
            item = with_perspective(apply_delivery(packet, d), framing).model_dump(mode="json")
            try:
                await ws.send_json({"type": "overlay", "item": item})
            except Exception:  # noqa: BLE001
                self.viewers.pop(ws, None)
        return [d.audit(packet) for d in chosen.values()]

    async def broadcast_fan_cue(self, cue: FanCue) -> None:
        for ws, prefs in list(self.viewers.items()):
            if prefs.access != "deaf":
                continue
            try:
                await ws.send_json({"type": "fan_cue", "cue": cue.model_dump(mode="json")})
            except Exception:  # noqa: BLE001
                self.viewers.pop(ws, None)


hub = Hub()
pipeline = MomentPipeline()


# ---------- approval loop ----------

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
    # No auto-approve path: automated actors may only hold, so their names cannot be used to air anything.
    if d.actor in SYSTEM_ACTORS and action != ProposalStatus.HELD:
        raise HTTPException(403, f"{d.actor} may only hold")
    return p


def _record_decision(p: OverlayProposal, action: ProposalStatus, d: Decision) -> DecisionLogEntry:
    p.status, p.decided_by, p.decided_at = action, d.actor, hub.now()
    if action == ProposalStatus.OVERRIDDEN:
        p.override_line = d.override_line
    entry = DecisionLogEntry(entry_id="d-" + uuid.uuid4().hex[:8], match_id=p.match_id, proposal_id=p.proposal_id,
                             action=action, actor=d.actor, at=p.decided_at, reasoning=d.reasoning,
                             package_id=p.package_id)
    hub.decisions.append(entry)
    return entry


def _fan_card(p: OverlayProposal) -> FanCard | None:
    if p.package_seq > 0:  # the deaf fan's caption travels with the lead graphic only
        return None
    card = hub.results.get(p.moment_id, {}).get("fan_card")
    return FanCard.model_validate(card) if card else None


def _delivery_plan(p: OverlayProposal) -> DeliveryPlan:
    m = hub.moments.get(p.moment_id)
    if is_code_built(p):
        # Stats and ticker lines are code from the official data, not AI: no variants or templates apply.
        return DeliveryPlan(variants=(), ctx=build_context(p, m, hub.meta), templates={}, is_high_stakes=False,
                            is_override=bool(p.override_line))
    variants = [NarrativeVariant.model_validate(v) for v in hub.results.get(p.moment_id, {}).get("variants", [])]
    templates = {lang: line for lang in get_args(Lang) if m and (line := template_line(m, lang, hub.meta))}
    # An override replaces the AI line for everyone, so neither variants nor templates of it may air.
    return DeliveryPlan(variants=tuple(variants), ctx=build_context(p, m, hub.meta), templates=templates,
                        is_high_stakes=bool(m and m.kind in HIGH_STAKES_KINDS), is_override=bool(p.override_line))


async def _air(p: OverlayProposal, approval: DecisionLogEntry) -> None:
    packet = attach_fan_card(build_packet(p, approval, hub.clock), _fan_card(p))
    hub.packets.append(packet)
    await hub.feed.publish("packet", packet)
    audits = await hub.broadcast_viewers(packet, _delivery_plan(p))
    hub.deliveries += audits
    await hub.broadcast_operators({"type": "deliveries", "proposal_id": p.proposal_id, "deliveries": audits})
    p.status = ProposalStatus.AIRED


async def _expire_stale() -> list[OverlayProposal]:
    """Held graphics the match has moved past leave the running order, with a log row for each."""
    expired = stale_proposals(hub.proposals.values(), hub.clock.play_ms, hub.now())
    for p in expired:
        seconds = shelf_life_ms(p) // 1000
        _record_decision(p, ProposalStatus.EXPIRED,
                         Decision(actor=EXPIRY_ACTOR,
                                  reasoning=f"no decision in time; the match moved {seconds} s past the moment"))
        await hub.broadcast_operators({"type": "proposal", "proposal": p.model_dump(mode="json")})
    return expired


async def _decide(proposal_id: str, action: ProposalStatus, d: Decision) -> OverlayProposal:
    await _expire_stale()  # a graphic that went stale while held cannot be fired late
    p = _open_proposal(proposal_id, action, d)
    entry = _record_decision(p, action, d)
    await hub.broadcast_operators({"type": "proposal", "proposal": p.model_dump(mode="json")})
    if action in AIRING_ACTIONS:
        await _air(p, entry)
    return p


def _without_override(d: Decision | None) -> Decision:
    """Replacement text is only accepted on /override, so an approve can never quietly change the line."""
    if d and d.override_line:
        raise HTTPException(422, "override_line is only accepted on /override")
    return d or Decision()


@app.post("/proposals/{proposal_id}/approve", response_model=OverlayProposal)
async def approve(proposal_id: str, d: Decision | None = None):
    return await _decide(proposal_id, ProposalStatus.APPROVED, _without_override(d))


@app.post("/proposals/{proposal_id}/hold", response_model=OverlayProposal)
async def hold(proposal_id: str, d: Decision | None = None):
    return await _decide(proposal_id, ProposalStatus.HELD, _without_override(d))


@app.post("/proposals/{proposal_id}/override", response_model=OverlayProposal)
async def override(proposal_id: str, d: Decision):
    if not d.override_line:
        raise HTTPException(422, "override_line required")
    return await _decide(proposal_id, ProposalStatus.OVERRIDDEN, d)


@app.post("/proposals/{proposal_id}/reject", response_model=OverlayProposal)
async def reject(proposal_id: str, d: Decision | None = None):
    return await _decide(proposal_id, ProposalStatus.REJECTED, _without_override(d))


# ---------- packages: several graphics, one decision ----------

PACKAGE_ACTIONS = {"approve": ProposalStatus.APPROVED, "hold": ProposalStatus.HELD, "reject": ProposalStatus.REJECTED}


def _package_items(package_id: str) -> list[OverlayProposal]:
    return sorted((p for p in hub.proposals.values() if p.package_id == package_id), key=lambda p: p.package_seq)


@app.get("/packages/{package_id}", response_model=list[OverlayProposal])
async def get_package(package_id: str):
    items = _package_items(package_id)
    if not items:
        raise HTTPException(404, "package not found")
    return items


@app.post("/packages/{package_id}/{action}", response_model=list[OverlayProposal])
async def decide_package(package_id: str, action: str, d: Decision | None = None):
    """One click applies the decision to every open item, in running order. Each item still gets its own
    decision row and its own approval id on the packet, so the gate and the audit trail are unchanged."""
    if action not in PACKAGE_ACTIONS:
        raise HTTPException(404, f"action must be one of {sorted(PACKAGE_ACTIONS)}")
    d = _without_override(d)
    await _expire_stale()  # choose what to fire only after stale items have left the running order
    items = _package_items(package_id)
    if not items:
        raise HTTPException(404, "package not found")
    open_items = [p for p in items if p.status in (ProposalStatus.PROPOSED, ProposalStatus.HELD)]
    if not open_items:
        raise HTTPException(409, "package already decided")
    return [await _decide(p.proposal_id, PACKAGE_ACTIONS[action], d) for p in open_items]


# ---------- preview before firing ----------

@app.get("/viewer-groups", response_model=list[ViewerGroup])
async def list_viewer_groups():
    """Options for the console's preview picker: persona x access x language x side."""
    return viewer_groups(settings.languages)


def _connected_views() -> list[ViewerPrefs]:
    """The viewer groups watching now, or the default viewer when nobody is connected."""
    seen: dict[str, ViewerPrefs] = {view_key(v): v for v in hub.viewers.values()}
    return list(seen.values()) or [DEFAULT_VIEW]


@app.get("/proposals/{proposal_id}/preview", response_model=Preview)
async def preview_proposal(proposal_id: str, view: Annotated[list[str] | None, Query()] = None,
                           override_line: Annotated[str | None, Query(min_length=1, max_length=280)] = None):
    """What the viewer groups the operator picks would see if this graphic were fired now, and why.

    `view` is repeatable, `persona.access.lang[.allegiance]`, e.g. `?view=fan.deaf.es&view=newcomer.none.hi.away`.
    With no `view`, previews the groups watching now. `override_line` previews a typed override.
    Read-only: builds no packet, logs no decision, sends nothing."""
    p = hub.proposals.get(proposal_id)
    if not p:
        raise HTTPException(404, "proposal not found")
    if len(view or []) > MAX_VIEWS:  # before parsing, so a huge request is refused cheaply
        raise HTTPException(422, f"pick at most {MAX_VIEWS} viewer groups")
    try:
        views = [parse_view(v) for v in view or []]
    except ValueError as ex:
        raise HTTPException(422, str(ex)) from ex
    plan = _delivery_plan(p)
    if override_line:
        plan = replace(plan, is_override=True)
    ctx = PreviewContext(state=hub.match_state, meta=hub.meta, override_line=override_line)
    return preview(p, plan, views or _connected_views(), ctx)


@app.get("/metrics", response_model=GalleryMetrics)
async def metrics():
    """Turnaround, error rate and operator workload for the match so far."""
    return gallery_metrics(hub.proposals, hub.decisions, hub.deliveries, hub.clock.play_ms, len(hub.packets))


@app.get("/decisions.csv")
async def decisions_csv():
    return Response(decisions_to_csv(hub.decisions), media_type="text/csv",
                    headers={"content-disposition": 'attachment; filename="decisions.csv"'})


@app.get("/proposals")
async def list_proposals(status: ProposalStatus | None = None):
    return [p for p in hub.proposals.values() if status is None or p.status == status]


@app.get("/deliveries")
async def deliveries():
    """Audit: for each approval, which text each viewer group received (variant/template/base) and why."""
    return hub.deliveries


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
    return {"ok": True, "speed": hub.replay_speed}


async def _auto_hold(proposal_id: str) -> None:
    """Approval SLA: a warning first, then a proposal nobody acts on is held, never aired.
    In Azure this is a Logic App."""
    warn_after = max(0.0, hub.auto_hold_s - hub.warn_s)
    await asyncio.sleep(warn_after)
    p = hub.proposals.get(proposal_id)
    if p and p.status == ProposalStatus.PROPOSED:
        await hub.broadcast_operators({"type": "sla_warning", "proposal_id": proposal_id, "package_id": p.package_id,
                                       "seconds_left": hub.auto_hold_s - warn_after,
                                       "hold_at": p.hold_at.isoformat() if p.hold_at else None})
    await asyncio.sleep(hub.auto_hold_s - warn_after)
    p = hub.proposals.get(proposal_id)
    if p and p.status == ProposalStatus.PROPOSED:
        held_for = f"no decision within {hub.auto_hold_s:g} s"
        await _decide(proposal_id, ProposalStatus.HELD, Decision(actor=SLA_ACTOR, reasoning=held_for))


# ---------- local replay (full pipeline in-process) ----------

class ReplayRequest(BaseModel):
    """A window of a recorded match, played at the speed the operator will really work at.

    `speed` defaults to 1.0 because that is the only speed a live feed has: compressing the match
    compresses the decision the gate exists to measure. To reach an interesting passage quickly,
    skip to it with `from_play_ms` rather than fast-forwarding through it. Events before the window
    are folded into match state without pacing and without proposing anything, so the desk joins a
    match already in progress with the right score, possession and form behind it — the same path a
    console takes when it connects to a live feed at half past three.
    """

    file: str = "data/match.jsonl"
    speed: float = Field(default=1.0, gt=0, description="Play time per real second when nothing is pending.")
    decision_speed: float | None = Field(
        default=1.0, gt=0,
        description="Speed to fall back to while the running order has something open, whatever `speed` is. "
                    "Real time by default: a decision put to a person is taken at the speed that person will "
                    "really have, and the match returns to `speed` once the running order is clear. Pass null "
                    "to keep one speed throughout, which is worth doing only to reproduce the old behaviour.")
    min_importance: float = 0.3
    from_play_ms: int = 0
    to_play_ms: int | None = None


@app.post("/matches/replay")
async def replay(req: ReplayRequest):
    path = Path(req.file)
    if not path.exists():
        raise HTTPException(404, f"{path} not found; run the simulator first")
    if hub.replay_task and not hub.replay_task.done():
        raise HTTPException(409, "a replay is already running")
    hub.replay_speed = None
    hub.replay_task = asyncio.create_task(_replay(req))
    return {"started": True}


async def _replay(req: ReplayRequest) -> None:
    """Drive the replay and, whatever happens, tell the console it is over.

    A console that is told nothing cannot tell a finished match from a hung one, and this runs as a
    detached task, so an exception here would otherwise stop the clock in silence.
    """
    try:
        await _drive_replay(req)
    except Exception as exc:  # noqa: BLE001
        logger.exception("replay failed")
        await _finish_replay(f"{type(exc).__name__}: {exc}")
    else:
        await _finish_replay(None)


async def _finish_replay(error: str | None) -> None:
    hub.replay_speed = None
    await hub.broadcast_operators({"type": "replay", "finished": True, "speed": None, "error": error,
                                   "clock": hub.clock.snapshot()})


async def _drive_replay(req: ReplayRequest) -> None:
    with Path(req.file).open(encoding="utf-8") as f:
        folder = await _start_match(MatchMeta.model_validate_json(f.readline()))
        warming = req.from_play_ms > 0
        for line in filter(str.strip, f):
            ev = MatchEvent.model_validate_json(line)
            gap_ms = hub.clock.advance(ev)  # the clock tracks the whole match, in the window or not
            if req.to_play_ms is not None and hub.clock.play_ms > req.to_play_ms:
                break
            if hub.clock.play_ms < req.from_play_ms:
                folder.apply(ev)  # fold the state, propose nothing: this is history, not a decision
                continue
            if warming:  # joining the match: the desk sees where it stands, and waits out no gap
                warming, gap_ms = False, 0
                await _publish_state(folder)
            await _replay_event(folder, ev, req, gap_ms)


async def _start_match(meta: MatchMeta) -> StateFolder:
    hub.new_match(meta)
    await hub.broadcast_operators({"type": "match", "meta": meta.model_dump(mode="json")})
    folder = StateFolder(meta)
    hub.match_state = folder.state
    return folder


async def _replay_event(folder: StateFolder, ev: MatchEvent, req: ReplayRequest,
                        gap_ms: int | None = None) -> None:
    # Pace on play time: the period clock restarts at half time, play time never does.
    await _pace(hub.clock.advance(ev) if gap_ms is None else gap_ms, req)
    await _expire_stale()
    moments = folder.apply(ev)
    if ev.seq % 10 == 0:
        await _publish_state(folder)
    for m in moments:
        if m.importance >= req.min_importance:
            await _handle_moment(_stamp_play_time(m))


PACING_SLICE_MS = 100  # the replay re-reads its speed this often, in real milliseconds


def _awaiting_decision() -> bool:
    """Is a person's answer outstanding right now?

    Only a proposal still on the desk counts. Once the timer has held one, the decision window has closed
    and the match carries on at the speed it was asked for — a held graphic lives out its shelf life while
    play runs normally. Counting held graphics here would pin an unattended desk at real time for ever.
    """
    return any(p.status == ProposalStatus.PROPOSED for p in hub.proposals.values())


def _effective_speed(req: ReplayRequest) -> float:
    """The speed the match is running at right now, which an open decision may have slowed."""
    if req.decision_speed is None or not _awaiting_decision():
        return req.speed
    return req.decision_speed


async def _pace(gap_ms: int, req: ReplayRequest) -> None:
    """Wait out the gap to the next event, re-reading the speed as it goes.

    Sliced rather than slept in one go, so a proposal that opens mid-gap slows the match down from that
    moment instead of the next event, and a decision taken mid-gap speeds it back up. The slices are real
    time, so a long gap at high speed costs no more wakeups than a short one.
    """
    left = float(max(0, gap_ms))
    while left > 0:
        speed = _effective_speed(req)
        await _announce_speed(speed)
        step = min(left, PACING_SLICE_MS * speed)
        await asyncio.sleep(step / 1000 / speed)
        left -= step


async def _announce_speed(speed: float) -> None:
    if speed == hub.replay_speed:
        return
    hub.replay_speed = speed
    await hub.broadcast_operators({"type": "replay", "speed": speed})


async def _publish_state(folder: StateFolder) -> None:
    hub.state = folder.state.model_dump(mode="json") | {"play_ms": hub.clock.play_ms}
    await hub.broadcast_operators({"type": "state", "state": hub.state, "clock": hub.clock.snapshot()})


def _stamp_play_time(m: Moment) -> Moment:
    """Ingest before v0.2 leaves Moment.play_ms at 0; the replay clock knows the real value."""
    return m if m.play_ms else m.model_copy(update={"play_ms": hub.clock.play_ms})


def _result_record(res: MomentResult) -> dict:
    # The card is built in code from the stats engine's facts; a workflow-built card, if one exists, wins.
    card: FanCard | None = getattr(res, "fan_card", None) or build_fan_card(res.moment, res.line, hub.meta)
    return {"explanation": res.explanation.model_dump(), "line": res.line,
            "variants": [v.model_dump(mode="json") for v in res.variants], "failures": res.failures,
            "fan_card": card.model_dump(mode="json") if card else None,
            "intel": getattr(res, "intel", None), "notes": getattr(res, "notes", [])}


async def _publish_fan_cue(m: Moment) -> None:
    cue = build_fan_cue(m, home_team=m.state.home.team)
    await hub.broadcast_fan_cue(cue)
    await hub.feed.publish("fan_cue", cue)


async def _handle_moment(m: Moment) -> None:
    if m.beat == "chance":
        # The cue is code and must air within 1 s, so it goes out before any agent call (up to ~8 s each).
        await _publish_fan_cue(m)
    res = await pipeline.process(m, meta=hub.meta)
    hub.moments[m.moment_id] = m
    hub.results[m.moment_id] = _result_record(res)
    await hub.broadcast_operators({"type": "moment", "moment": m.model_dump(mode="json", exclude={"state"}),
                                   **hub.results[m.moment_id]})
    if res.proposal:
        flagged = unsourced_numbers(res.proposal.line, m)
        lead = _from_agent(res.proposal).model_copy(update={"proposed_at": hub.now(), "unsourced_numbers": flagged})
        for p in build_goal_package(lead, m, hub.meta):
            await _queue_proposal(p)


# Decision, package and timing fields belong to the API. The producer agent writes only a ProducerDecision and
# the agents' code builds the OverlayProposal, so these fields arrive at their defaults; resetting them anyway
# keeps the API safe from any pipeline (e.g. a package_id that would make a graphic fire with someone else's
# one-click package).
_API_OWNED = ("status", "decided_by", "decided_at", "override_line", "proposed_at", "proposed_play_ms", "warn_at",
              "hold_at", "package_id", "package_seq", "package_offset_ms", "item_label", "unsourced_numbers")


def _from_agent(p: OverlayProposal) -> OverlayProposal:
    return p.model_copy(update={name: OverlayProposal.model_fields[name].get_default(call_default_factory=True)
                                for name in _API_OWNED})


async def _queue_proposal(p: OverlayProposal) -> None:
    proposed_at = p.proposed_at or hub.now()
    warn_at, hold_at = sla_times(proposed_at, hub.auto_hold_s, hub.warn_s)
    p = p.model_copy(update={"proposed_at": proposed_at, "proposed_play_ms": hub.clock.play_ms,
                             "warn_at": warn_at, "hold_at": hold_at})
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
async def ws_viewer(ws: WebSocket, persona: str = "fan", access: Access = "none", lang: Lang = "en",
                    allegiance: Allegiance = "neutral"):
    try:
        persona_value, access_value = parse_viewer(persona, access)
    except ValueError:
        logger.warning("viewer refused: unknown persona", extra={"crq.param": "persona"})
        await ws.close(code=1008)
        return
    await ws.accept()
    hub.viewers[ws] = ViewerPrefs(persona=persona_value, access=access_value, lang=lang, allegiance=allegiance)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.viewers.pop(ws, None)

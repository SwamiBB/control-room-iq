"""Control Room IQ API: operator console, approval loop, overlay feed, viewer feeds.

Local mode (default): `uvicorn api.main:app --reload` then POST /matches/replay with a match file to
run the full pipeline in-process (simulator -> stats -> agents -> proposals -> approvals -> overlay).
In Azure the replay runs the same way, inside this service; approved items also go to the `crq-overlay`
Event Hub, and every decision is also written to Cosmos DB (`decision_store.py`). The hub below holds the
current run in memory.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, get_args

from agents import telemetry
from agents.config import settings
from agents.telemetry import brief, tracer
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
    MomentKind,
    NarrativeVariant,
    OverlayPacket,
    OverlayProposal,
    ProposalStatus,
    Recap,
)
from fastapi import FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from ingest.stats import StateFolder
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import Link, SpanContext, Status, StatusCode
from pydantic import BaseModel, Field

from .clock import PlayClock
from .content_safety import check_override, close_content_safety
from .decision_store import DecisionStore, decision_store_from_env
from .delivery import HIGH_STAKES_KINDS, Delivery, DeliveryPlan, apply_delivery, choose_delivery
from .exports import decisions_to_csv, history_to_csv
from .fallback_text import template_line
from .fan_card import build_fan_card
from .fan_cue import build_fan_cue
from .feed import OverlayFeed, eventhubs_sink_from_env
from .goal_package import build_goal_package, is_code_built
from .guards import (
    DECISIONS_PER_MINUTE,
    MAX_REPLAY_SPEED,
    OVERRIDES_PER_MINUTE,
    REPLAY_COOLDOWN_S,
    DailyBudget,
    RateWindow,
    retry_after,
)
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
from .scheduler import Placement, hold_advice, place
from .timing import (
    EXPIRY_ACTOR,
    SLA_ACTOR,
    SLA_HOLD_S,
    SLA_WARN_S,
    SUPERSEDE_ACTOR,
    SYSTEM_ACTORS,
    shelf_life_ms,
    sla_times,
    stale_proposals,
)
from .tracking_feed import TrackingFeed, load_tracking
from .variant_checks import build_context, unsourced_numbers


@asynccontextmanager
async def lifespan(_: FastAPI):
    sink = eventhubs_sink_from_env()
    if sink:
        hub.feed.sinks.append(sink)
    store = decision_store_from_env()
    if store:
        store.start()
        hub.store = store
    yield
    if store:
        await store.close()  # drains first; anything recorded after that is logged as not persisted
        hub.store = None
    if sink:
        await sink.close()
    await close_content_safety()


logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    # Uvicorn configures only its own loggers; without this, app warnings (agent fallbacks, sink failures)
    # reach stderr bare, with no time or source. Before tracing starts: Azure Monitor adds its own handler to the
    # root logger, which would skip this and leave the console without the app's warnings.
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
telemetry.configure("crq-api")
app = FastAPI(title="Control Room IQ API", version="0.2.0", lifespan=lifespan)
telemetry.instrument_app(app)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["x-crq-run-id"])


MAX_PARALLEL_MOMENTS = 3  # agent pipelines allowed to run at once beside the replay


def _new_run_id() -> str:
    """One replay of a match. Replaying the same match reuses its moment ids, so the run keeps the log apart."""
    return f"r-{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"


class Hub:
    """In-memory state and fan-out for the current run; decisions are also persisted (`store`, when configured)."""

    def __init__(self) -> None:
        self.store: DecisionStore | None = None  # outlives reset() and new_match(): it holds every run
        self.reset()

    def new_run(self) -> None:
        """The persisted log tells runs of the same match apart, and numbers each run's decisions from 1."""
        self.run_id, self.decision_seq = _new_run_id(), 0

    def reset(self) -> None:
        self.now: Callable[[], datetime] = lambda: datetime.now(UTC)
        self.proposals: dict[str, OverlayProposal] = {}
        self.decisions: list[DecisionLogEntry] = []
        self.new_run()
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
        self.state_published_at = 0.0  # time.monotonic() of the last state message, so a new match publishes at once
        self.moment_tasks: set[asyncio.Task] = set()  # agent pipelines running beside the replay (#51)
        self.moment_slots = asyncio.Semaphore(MAX_PARALLEL_MOMENTS)
        self.goal_phases: set[str] = set()  # moves that ended in a goal: their other cards are superseded (#50)
        self.moment_traces: dict[str, SpanContext] = {}  # moment_id -> its trace, which decisions and airings link to
        # The console is open during judging (synthetic data only): limits far above what a person at it does.
        self.decision_rate = RateWindow(DECISIONS_PER_MINUTE)
        self.override_rate = RateWindow(OVERRIDES_PER_MINUTE)
        self.replay_finished_at: float | None = None  # time.monotonic() when the last replay ended
        self.budget = DailyBudget()
        # The replay moves the clock to the next event before waiting out the gap; this is how far the match
        # itself still is from it, so placement and queued graphics use the live play time (`live_ms`).
        self.pace_left_ms = 0.0
        self.air_tasks: set[asyncio.Task] = set()  # queued graphics waiting for their slot
        self.tracking: TrackingFeed | None = None  # the match's positions for the viewers, if it has a tracking file
        self.tracking_index: int | None = None  # the frame last sent
        self.tracking_sent_at = 0.0  # time.monotonic() of that send

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
        # Cleared at once: /recap and perspective must not see the previous match's state behind the new meta while
        # the new folder loads.
        self.match_state = None
        self.new_run()  # "Run again" is a new run in the persisted log
        self.replay_speed = None
        self.state_published_at = 0.0
        self.cancel_moments()  # the old match's agents must not post into the new one
        self.moment_slots = asyncio.Semaphore(MAX_PARALLEL_MOMENTS)  # a fresh one per match (and event loop)
        self.goal_phases.clear()
        self.moment_traces.clear()  # a replayed match reuses moment ids: its decisions must not link to the last run
        self.tracking, self.tracking_index, self.tracking_sent_at = None, None, 0.0

    def cancel_moments(self) -> None:
        for task in self.moment_tasks | self.air_tasks:  # queued graphics of the old match must not air either
            task.cancel()
        self.moment_tasks.clear()
        self.air_tasks.clear()

    def live_ms(self) -> int:
        """Play time as the match is now, not the next event's time the clock already reads."""
        return self.clock.play_ms - int(self.pace_left_ms)

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
            delivered = with_perspective(apply_delivery(packet, d), framing)
            if prefs.access != "deaf":  # the caption card is the deaf-access path, like the strike cue (#54)
                delivered = delivered.model_copy(update={"fan_card": None})
            item = delivered.model_dump(mode="json")
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

    async def broadcast_tracking(self, frame: dict) -> None:
        """The players and the ball, to every viewer: match data, not generated text, so no approval gate."""
        for ws in list(self.viewers):
            try:
                await ws.send_json({"type": "tracking", "frame": frame})
            except Exception:  # noqa: BLE001
                self.viewers.pop(ws, None)


hub = Hub()
pipeline = MomentPipeline()
templates = MomentPipeline(with_models=False)  # once the day's model budget is spent


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
    hub.decision_seq += 1
    if hub.store:  # the durable copy, written in the background: the decision never waits on it
        hub.store.add(entry, hub.run_id, hub.decision_seq)
    # The run joins a trace to its rows in the persisted log (/decisions.csv?run=<id>, Cosmos DB).
    attrs = {"crq.run_id": hub.run_id, "crq.decision_id": entry.entry_id, "crq.moment_id": p.moment_id,
             "crq.proposal_id": p.proposal_id, "crq.action": action.value,
             "crq.actor": d.actor, "crq.layer": p.layer.value}
    if p.package_id:
        attrs["crq.package_id"] = p.package_id
    if p.proposed_at:
        attrs["crq.seconds_on_desk"] = round((entry.at - p.proposed_at).total_seconds(), 2)
    # Inside an operator's request it sits beside the airing it caused; from the timer or a goal it is its own trace.
    # Either way it links to the moment's trace.
    tracer.start_span("crq.decision", links=_links(p.moment_id), attributes=attrs).end()
    return entry


def _links(moment_id: str) -> list[Link]:
    """A decision or an airing happens later, in its own trace: a link takes it back to the moment's agents."""
    ctx = hub.moment_traces.get(moment_id)
    return [Link(ctx)] if ctx else []


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


async def _air(p: OverlayProposal, approval: DecisionLogEntry, run_id: str, links: list[Link]) -> None:
    """`run_id` and `links` are the decision's, taken when it was made (see _decide)."""
    with tracer.start_as_current_span("crq.air", links=links, attributes={
            "crq.moment_id": p.moment_id, "crq.proposal_id": p.proposal_id, "crq.layer": p.layer.value,
            "crq.approval_id": approval.entry_id, "crq.run_id": run_id}) as span:
        slot = _place(p)  # against what is on air now: the card may have waited on the desk
        p.t_in_ms, p.t_out_ms = slot.t_in_ms, slot.t_out_ms
        p.replaces = list(dict.fromkeys([*p.replaces, *slot.replaces]))
        span.set_attributes({"crq.wait_ms": slot.t_in_ms - hub.live_ms(), "crq.late": slot.late,
                             "crq.cuts": len(slot.replaces), "crq.placement": slot.reason or "on air at once"})
        packet = attach_fan_card(build_packet(p, approval, hub.clock), _fan_card(p))
        hub.packets.append(packet)  # on the schedule now, so the next placement sees it
        # The console's running order shows the slot it was given now, not the one from when it reached the desk.
        await hub.broadcast_operators({"type": "proposal", "proposal": p.model_dump(mode="json")})
        if packet.t_in_ms > hub.live_ms() and hub.replay_speed is not None:
            # Viewers show a packet as it arrives, so a queued one is sent when the match reaches its slot.
            task = _background(_send_when_due(p, packet, links))
            hub.air_tasks.add(task)
            task.add_done_callback(hub.air_tasks.discard)
            return
        _record_audits(span, await _send(p, packet))


def _place(p: OverlayProposal) -> Placement:
    def moment_of(proposal_id: str) -> str | None:
        return q.moment_id if (q := hub.proposals.get(proposal_id)) else None

    return place(p, hub.packets, hub.live_ms(), hub.moments.get(p.moment_id), moment_of,
                 clock_running=hub.replay_speed is not None)


def _record_audits(span, audits: list[dict]) -> None:
    for source in ("variant", "template", "base", "override"):
        span.set_attribute(f"crq.groups.{source}", sum(a["source"] == source for a in audits))
    for a in audits:  # what each viewer group got, and why not its own version
        span.add_event("delivered", {"crq.group": f'{a["persona"]}.{a["access"]}.{a["lang"]}',
                                     "crq.source": a["source"], "crq.failures": a["failures"]})


async def _send_when_due(p: OverlayProposal, packet: OverlayPacket, links: list[Link]) -> None:
    """Waits for the match to reach the packet's slot, then sends it. A graphic that something placed after it
    replaces is never sent, and comes off the schedule (so it isn't counted as aired). When the replay stops, a
    waiting graphic that nothing replaces goes at once rather than never."""
    while (speed := hub.replay_speed) is not None and (left := packet.t_in_ms - hub.live_ms()) > 0:
        await asyncio.sleep(min(1.0, max(0.05, left / 1000 / speed)))
    if packet not in hub.packets:
        return  # a new match
    if any(packet.cue_id in q.replaces for q in hub.packets if q is not packet):
        hub.packets.remove(packet)
        return
    with tracer.start_as_current_span("crq.air", links=links, attributes={
            "crq.moment_id": p.moment_id, "crq.proposal_id": p.proposal_id, "crq.layer": p.layer.value,
            "crq.approval_id": packet.approval_id, "crq.queued": True}) as span:
        _record_audits(span, await _send(p, packet))


async def _send(p: OverlayProposal, packet: OverlayPacket) -> list[dict]:
    p.status = ProposalStatus.AIRED  # only now: a queued graphic is approved until it is actually on air
    await hub.broadcast_operators({"type": "proposal", "proposal": p.model_dump(mode="json")})
    await hub.feed.publish("packet", packet)
    audits = await hub.broadcast_viewers(packet, _delivery_plan(p))
    hub.deliveries += audits
    await hub.broadcast_operators({"type": "deliveries", "proposal_id": p.proposal_id, "deliveries": audits})
    return audits


async def _expire_stale() -> list[OverlayProposal]:
    """Held graphics the match has moved past leave the running order, with a log row for each."""
    expired = stale_proposals(hub.proposals.values(), hub.clock.play_ms, hub.now())
    for p in expired:
        if hub.proposals.get(p.proposal_id) is not p:
            continue  # "Run again" landed during a broadcast below: the card belongs to the previous run
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
    # Taken now, with the decision: a new run can start during the broadcast below, and the airing belongs to this one.
    run_id, links = hub.run_id, _links(p.moment_id)
    await hub.broadcast_operators({"type": "proposal", "proposal": p.model_dump(mode="json")})
    if action in AIRING_ACTIONS:
        await _air(p, entry, run_id, links)
    return p


def _without_override(d: Decision | None) -> Decision:
    """Replacement text is only accepted on /override, so an approve can never quietly change the line."""
    if d and d.override_line:
        raise HTTPException(422, "override_line is only accepted on /override")
    return d or Decision()


def _limit(window: RateWindow, what: str) -> None:
    if (wait := window.take()) is not None:
        raise HTTPException(429, f"too many {what}; try again in {round(wait)} s", headers=retry_after(wait))


def _limit_decision(proposal_id: str, *windows: tuple[RateWindow, str]) -> None:
    """Counts only a decision on a real card still open: requests for made-up or already decided cards are
    refused by _decide without using the shared limit, so they can't lock the operator out."""
    p = hub.proposals.get(proposal_id)
    if p is None or p.status not in (ProposalStatus.PROPOSED, ProposalStatus.HELD):
        return
    for window, what in windows or ((hub.decision_rate, "decisions"),):
        _limit(window, what)


@app.post("/proposals/{proposal_id}/approve", response_model=OverlayProposal)
async def approve(proposal_id: str, d: Decision | None = None):
    _limit_decision(proposal_id)
    return await _decide(proposal_id, ProposalStatus.APPROVED, _without_override(d))


@app.post("/proposals/{proposal_id}/hold", response_model=OverlayProposal)
async def hold(proposal_id: str, d: Decision | None = None):
    _limit_decision(proposal_id)
    return await _decide(proposal_id, ProposalStatus.HELD, _without_override(d))


@app.post("/proposals/{proposal_id}/override", response_model=OverlayProposal)
async def override(proposal_id: str, d: Decision):
    if not d.override_line:
        raise HTTPException(422, "override_line required")
    _open_proposal(proposal_id, ProposalStatus.OVERRIDDEN, d)  # a missing or decided card: no paid check, no limit
    _limit_decision(proposal_id, (hub.override_rate, "overrides"), (hub.decision_rate, "decisions"))
    await check_override(d.override_line)  # before anything is recorded or aired; fails closed in Azure
    return await _decide(proposal_id, ProposalStatus.OVERRIDDEN, d)


@app.post("/proposals/{proposal_id}/reject", response_model=OverlayProposal)
async def reject(proposal_id: str, d: Decision | None = None):
    _limit_decision(proposal_id)
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
    _limit(hub.decision_rate, "decisions")  # one click on a real, open package, however many items it fires
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


RUN_PATTERN = r"^(all|r-[0-9A-Za-z-]{1,40})$"  # a run id from _new_run_id(), or "all"


@app.get("/decisions.csv")
async def decisions_csv(run: Annotated[str | None, Query(pattern=RUN_PATTERN)] = None):
    """The current run's log, as the console shows it. `?run=<run id>` or `?run=all` reads the persisted log
    instead, which outlives "Run again" and restarts. That needs Cosmos DB: 503 when the API runs without it."""
    if run is None:
        return Response(decisions_to_csv(hub.decisions), media_type="text/csv",
                        headers={"content-disposition": 'attachment; filename="decisions.csv"',
                                 "x-crq-run-id": hub.run_id})
    if hub.store is None:
        raise HTTPException(503, "the persisted decision log needs Cosmos DB, which this API is running without")
    try:
        docs = await hub.store.history(None if run == "all" else run)
    except Exception as ex:  # noqa: BLE001 - an outage or a role problem: say so, don't 500
        logger.exception("reading the persisted decision log failed")
        raise HTTPException(503, f"the persisted decision log could not be read ({type(ex).__name__})") from ex
    name = "decisions-all.csv" if run == "all" else f"decisions-{run}.csv"
    return Response(history_to_csv(docs), media_type="text/csv",
                    headers={"content-disposition": f'attachment; filename="{name}"'})



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

    file: str = "data/reference/match-042.jsonl"  # bundled in the image (#13)
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


# Replays read only match files under data/: the bundled reference matches, or one generated locally. A path from
# the request is never opened outside it, so a caller can't probe the filesystem or have another file's contents
# echoed back in a parse error (#22).
REPLAY_ROOT = Path("data").resolve()


@app.post("/matches/replay")
async def replay(req: ReplayRequest):
    path = Path(req.file)
    resolved = path.resolve()
    if path.suffix != ".jsonl" or not resolved.is_relative_to(REPLAY_ROOT):
        raise HTTPException(422, "replay a .jsonl match under data/, e.g. data/reference/match-042.jsonl")
    if not path.exists():
        raise HTTPException(404, f"{path} not found; replay a match in data/reference/, or generate one with "
                                 "the simulator")
    if hub.replay_task and not hub.replay_task.done():
        raise HTTPException(409, "a replay is already running")
    # Over HTTP, no faster than the console's fastest (50x): a faster replay would produce moments, and spend the
    # day's model budget, faster than anyone could watch.
    if max(req.speed, req.decision_speed or 0) > MAX_REPLAY_SPEED:
        raise HTTPException(422, f"replay speed is at most {MAX_REPLAY_SPEED:g}x")
    if hub.replay_finished_at is not None and (wait := REPLAY_COOLDOWN_S - (time.monotonic()
                                                                          - hub.replay_finished_at)) > 0:
        raise HTTPException(429, f"the last replay just ended; start another in {round(wait)} s",
                            headers=retry_after(wait))
    hub.replay_speed = None
    hub.replay_task = _background(_replay(req))
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
        hub.cancel_moments()  # a failed replay must not keep adding cards behind a "finished" console
        await _finish_replay(f"{type(exc).__name__}: {exc}")
    else:
        await _finish_replay(None)


async def _finish_replay(error: str | None) -> None:
    hub.replay_speed = None
    if error is None:  # after a failed replay, "Run again" works at once
        hub.replay_finished_at = time.monotonic()
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
    # The last moments' agents may still be writing: the replay is finished once their cards are on the desk.
    await _drain_moments()


async def _start_match(meta: MatchMeta) -> StateFolder:
    hub.new_match(meta)
    await hub.broadcast_operators({"type": "match", "meta": meta.model_dump(mode="json")})
    # Building the folder loads the match's tracking file (about 1 s); off the event loop, sockets keep flowing (#42).
    # The viewers' positions come from the same file, read alongside.
    folder, hub.tracking = await asyncio.gather(asyncio.to_thread(StateFolder, meta),
                                                asyncio.to_thread(load_tracking, meta))
    hub.match_state = folder.state
    return folder


async def _replay_event(folder: StateFolder, ev: MatchEvent, req: ReplayRequest,
                        gap_ms: int | None = None) -> None:
    # Pace on play time: the period clock restarts at half time, play time never does.
    await _pace(hub.clock.advance(ev) if gap_ms is None else gap_ms, req)
    await _expire_stale()
    moments = folder.apply(ev)
    if ev.seq % 10 == 0 or time.monotonic() - hub.state_published_at >= STATE_PUBLISH_S:
        hub.state_published_at = time.monotonic()
        await _publish_state(folder)
    for m in moments:
        if m.importance >= req.min_importance:
            await _start_moment(_stamp_play_time(m))


PACING_SLICE_MS = 100  # the replay re-reads its speed this often, in real milliseconds
# State goes out every tenth event or this often in real time, whichever comes first: ten events are a blink
# at speed 20 but about four seconds at real time, long enough for the console's play clock to look frozen.
STATE_PUBLISH_S = 0.25


def _awaiting_decision() -> bool:
    """Is a person's answer outstanding right now, or about to be?

    A proposal still on the desk counts, and so do agents still writing one: at full speed the ~15 s they
    take would let minutes of match go by, and the card would reach the desk long after its moment (#51).
    Once the timer has held a graphic, the decision window has closed and the match carries on at the speed
    it was asked for — counting held graphics here would pin an unattended desk at real time for ever.
    """
    return bool(hub.moment_tasks) or any(p.status == ProposalStatus.PROPOSED for p in hub.proposals.values())


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
    left = hub.pace_left_ms = float(max(0, gap_ms))
    try:
        while left > 0:
            speed = _effective_speed(req)
            await _announce_speed(speed)
            step = min(left, PACING_SLICE_MS * speed)
            await asyncio.sleep(step / 1000 / speed)
            left = hub.pace_left_ms = left - step
            # The clock already reads the next event's time; the match itself is `left` short of it.
            await _send_tracking(hub.live_ms())
    finally:
        hub.pace_left_ms = 0.0


TRACKING_SEND_S = 0.2  # at most this often in real time: every frame at real time (4 a second), a sample faster


async def _send_tracking(play_ms: int) -> None:
    """The viewers' players and ball as they are at play_ms, when that is a frame they have not had yet."""
    if hub.tracking is None or not hub.viewers:
        return
    i = hub.tracking.index_at(play_ms)
    now = time.monotonic()
    if i is None or i == hub.tracking_index or now - hub.tracking_sent_at < TRACKING_SEND_S:
        return
    hub.tracking_index, hub.tracking_sent_at = i, now
    await hub.broadcast_tracking(hub.tracking.frame(i))


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


def _phase_of(m: Moment) -> str | None:
    return m.state.current_phase.phase_id if m.state.current_phase else None


async def _start_moment(m: Moment) -> None:
    """Hand a moment to the agents without stopping the match (#51).

    The strike beat is code only: the deaf fan's cue goes out at once and no agent runs, because the result
    beat a moment later writes the card (#50, design §5.1). A goal takes over the pending cards of its move
    as soon as it happens, not when its own agents finish.
    """
    if m.beat == "chance":
        await _publish_fan_cue(m)
        return
    if m.kind == MomentKind.GOAL and (phase := _phase_of(m)):
        hub.goal_phases.add(phase)
        await _supersede(phase, m)
    task = _background(_run_moment(m))
    hub.moment_tasks.add(task)
    task.add_done_callback(hub.moment_tasks.discard)


def _background(coro) -> asyncio.Task:
    """A task that outlives the span it was started in (a replay, a moment, the timer): it starts with no current
    span, so it can't keep adding to a request's trace long after the request ended."""
    token = otel_context.attach(otel_context.Context())
    try:
        return asyncio.create_task(coro)
    finally:
        otel_context.detach(token)


async def _run_moment(m: Moment) -> None:
    # One trace per moment: the agents' spans nest inside; its decisions and airings link back to it. It starts
    # before the wait for a free slot, so a moment that queued shows why its card was late.
    waiting = time.perf_counter()
    with tracer.start_as_current_span("crq.moment", context=otel_context.Context(), attributes={
            "crq.run_id": hub.run_id, "crq.moment_id": m.moment_id, "crq.match_id": m.match_id,
            "crq.kind": m.kind.value, "crq.beat": m.beat, "crq.clock": _clock(m),
            "crq.importance": m.importance}) as span:
        hub.moment_traces[m.moment_id] = span.get_span_context()
        try:
            async with hub.moment_slots:
                span.set_attribute("crq.slot_wait_ms", round((time.perf_counter() - waiting) * 1000))
                await _handle_moment(m)
        except asyncio.CancelledError:
            span.set_attribute("crq.cancelled", True)  # a new match replaced this one: not a failure
            raise
        except Exception as ex:  # noqa: BLE001 - one moment's failure must not stop the match
            _record_failure(span, ex)
            logger.exception("moment %s failed", m.moment_id)


def _record_failure(span, ex: Exception) -> None:
    span.record_exception(ex)
    span.set_status(Status(StatusCode.ERROR, brief(f"{type(ex).__name__}: {ex}")))


async def _drain_moments() -> None:
    while hub.moment_tasks:
        await asyncio.gather(*list(hub.moment_tasks), return_exceptions=True)


async def _supersede(phase: str, goal: Moment) -> None:
    """Pending cards from the move that just ended in a goal leave the desk, with a log row for each."""
    for p in list(hub.proposals.values()):
        pm = hub.moments.get(p.moment_id)
        if p.status == ProposalStatus.PROPOSED and pm and pm.kind != MomentKind.GOAL and _phase_of(pm) == phase:
            _record_decision(p, ProposalStatus.EXPIRED,
                             Decision(actor=SUPERSEDE_ACTOR, reasoning=f"superseded by the goal at {_clock(goal)}"))
            await hub.broadcast_operators({"type": "proposal", "proposal": p.model_dump(mode="json")})


def _clock(m: Moment) -> str:
    """The match minute as viewers know it: the period clock restarts at half time, the match minute does not."""
    minute = m.t_ms // 60000 + (45 if m.period == 2 else 0)
    return f"{minute:02d}:{m.t_ms // 1000 % 60:02d}"


GOAL_TOOK_OVER = "No graphic proposed: the goal on the same move took over"
BUDGET_PAUSE = "Templates used: today's model budget ({limit} moments) is spent; the agents resume tomorrow (UTC)"


def _taken_by_goal(m: Moment) -> bool:
    return m.kind != MomentKind.GOAL and _phase_of(m) in hub.goal_phases


async def _handle_moment(m: Moment) -> None:
    called = False
    queued = False
    dropped = False  # the goal on this move took the card over

    async def on_card(card: MomentResult) -> None:
        """The card goes on the desk as soon as the producer writes it; the translations follow (#90)."""
        nonlocal called, queued, dropped
        called = True
        if not with_models:
            card.notes.append(BUDGET_PAUSE.format(limit=hub.budget.limit))
        hub.moments[m.moment_id] = m
        # A record before the versions exist, so a preview or a fire in the meantime has the line, the deaf fan's
        # card and the templates; a viewer's own version falls back until the translations arrive.
        hub.results[m.moment_id] = _result_record(card)
        if card.proposal is None:
            return
        if _taken_by_goal(m):  # the goal on this move arrived while the agents were writing
            dropped = True
            return
        await _queue_card(card.proposal, m)
        queued = True  # only once it is on the desk: a queueing error fails the moment as a whole
        trace.get_current_span().add_event("card on the desk", {
            "crq.proposal_id": card.proposal.proposal_id, "crq.layer": card.proposal.layer.value,
            "crq.template": card.proposal.fallback})

    try:
        with_models = hub.budget.take()
        trace.get_current_span().set_attribute("crq.models", with_models)
        res = await (pipeline if with_models else templates).process(m, meta=hub.meta, on_card=on_card)
        if not with_models and not any(n.startswith("Templates used") for n in res.notes):
            res.notes.append(BUDGET_PAUSE.format(limit=hub.budget.limit))
        if not called:  # a pipeline without the early hand-over (test stand-ins): the card goes on the desk now
            await on_card(res)
    except Exception as ex:
        if not queued:
            raise  # nothing reached the desk: the moment fails as a whole, as before
        # The card is already on the desk: keep its record and tell the operators, rather than leave it orphaned.
        logger.exception("moment %s: the versions failed after the card was queued", m.moment_id)
        record = hub.results.setdefault(m.moment_id, {})
        record["failures"] = [*record.get("failures", []), "versions: failed after the card; templates used"]
        span = trace.get_current_span()
        _record_failure(span, ex)
        span.set_attribute("crq.card", True)
        span.set_attribute("crq.failure_reasons", [brief(r) for r in record["failures"]])
        await hub.broadcast_operators({"type": "moment", "moment": m.model_dump(mode="json", exclude={"state"}),
                                       **record})
        return
    if res.proposal and not queued and (dropped or _taken_by_goal(m)):
        res.notes.append(GOAL_TOOK_OVER)
        res.proposal = None
    hub.moments[m.moment_id] = m
    hub.results[m.moment_id] = _result_record(res)
    span = trace.get_current_span()
    span.set_attribute("crq.card", bool(queued))
    span.set_attribute("crq.versions", len(res.variants))
    span.set_attribute("crq.failures", len(res.failures))
    if res.failures:  # every template fallback in this moment and why, including those decided after a call
        span.set_attribute("crq.failure_reasons", [brief(r) for r in res.failures])
    await hub.broadcast_operators({"type": "moment", "moment": m.model_dump(mode="json", exclude={"state"}),
                                   **hub.results[m.moment_id]})
    # A graphic fired before the versions existed keeps the text it aired with (a template in the viewer's
    # language, or the English line): on-air text is never swapped mid-read. Later fires carry the versions.


async def _queue_card(proposal: OverlayProposal, m: Moment) -> None:
    # unsourced_numbers catches AI mistakes; template-fallback and code-built lines are authored in this
    # repo (templates in fallback_text.py, goal routines in goal_package.py, speed/stat milestones in
    # ingest), so their numbers are trustworthy by construction and the flag would be a false positive.
    model_authored = not proposal.fallback and proposal.meta.routing != "template"
    flagged = unsourced_numbers(proposal.line, m) if model_authored else []
    lead = _from_agent(proposal).model_copy(update={"proposed_at": hub.now(), "unsourced_numbers": flagged})
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
    # Where it would go if fired now, so the running order shows a real slot; placed again when it is fired.
    slot = _place(p)
    advice = p.hold_advice if p.hold_advice.recommend_hold else hold_advice(hub.moments.get(p.moment_id),
                                                                            hub.live_ms())
    p = p.model_copy(update={"t_in_ms": slot.t_in_ms, "t_out_ms": slot.t_out_ms, "hold_advice": advice})
    hub.proposals[p.proposal_id] = p
    await hub.broadcast_operators({"type": "proposal", "proposal": p.model_dump(mode="json")})
    _background(_auto_hold(p.proposal_id))


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

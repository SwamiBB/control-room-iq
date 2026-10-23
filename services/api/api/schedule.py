"""Read-only view of what is on each overlay layer and what is queued, for the operator console.

This reports the schedule; it does not make placement decisions (that is the scheduler module's job).
It applies the renderer's rules so the console shows what viewers see: upsert by cue_id, and a packet
leaves air once a packet that `replaces` it has started.
"""

from __future__ import annotations

from collections.abc import Iterable

from crq_schemas import OverlayLayer, OverlayPacket, OverlayProposal, ProposalStatus
from pydantic import BaseModel, Field

from .clock import PlayClock


class LayerSchedule(BaseModel):
    on_air: list[OverlayPacket] = Field(default_factory=list)
    queued: list[OverlayPacket] = Field(default_factory=list)


class ScheduleView(BaseModel):
    clock: dict[str, int]
    layers: dict[OverlayLayer, LayerSchedule]
    awaiting_decision: list[OverlayProposal]


def _latest_by_cue(packets: Iterable[OverlayPacket]) -> list[OverlayPacket]:
    latest: dict[str, OverlayPacket] = {}
    for p in packets:
        latest[p.cue_id] = p
    return list(latest.values())


def _replaced(packets: list[OverlayPacket], now: int) -> set[str]:
    return {cue for p in packets if p.t_in_ms <= now for cue in p.replaces}


def _layers(packets: list[OverlayPacket], now: int) -> dict[OverlayLayer, LayerSchedule]:
    layers = {layer: LayerSchedule() for layer in OverlayLayer}
    gone = _replaced(packets, now)
    for p in sorted(packets, key=lambda p: (p.t_in_ms, p.priority)):
        if p.cue_id in gone or p.t_out_ms <= now:
            continue
        bucket = layers[p.layer].on_air if p.t_in_ms <= now else layers[p.layer].queued
        bucket.append(p)
    return layers


def build_schedule(packets: Iterable[OverlayPacket], proposals: Iterable[OverlayProposal],
                   clock: PlayClock) -> ScheduleView:
    awaiting = sorted((p for p in proposals if p.status == ProposalStatus.PROPOSED), key=lambda p: p.priority)
    return ScheduleView(clock=clock.snapshot(), layers=_layers(_latest_by_cue(packets), clock.play_ms),
                        awaiting_decision=awaiting)

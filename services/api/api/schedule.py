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


def latest_by_cue(packets: Iterable[OverlayPacket]) -> list[OverlayPacket]:
    latest: dict[str, OverlayPacket] = {}
    for p in packets:
        latest[p.cue_id] = p
    return list(latest.values())


def live_packets(packets: Iterable[OverlayPacket], now: int) -> list[OverlayPacket]:
    """On air or queued, as the renderer sees it: the latest per cue, not yet over, and not taken down by a
    packet that replaces it and has started. The scheduler places against the same list."""
    latest = latest_by_cue(packets)
    gone = {cue for p in latest if p.t_in_ms <= now for cue in p.replaces}
    return [p for p in latest if p.cue_id not in gone and p.t_out_ms > now]


def _layers(packets: list[OverlayPacket], now: int) -> dict[OverlayLayer, LayerSchedule]:
    layers = {layer: LayerSchedule() for layer in OverlayLayer}
    for p in sorted(live_packets(packets, now), key=lambda p: (p.t_in_ms, p.priority)):
        bucket = layers[p.layer].on_air if p.t_in_ms <= now else layers[p.layer].queued
        bucket.append(p)
    return layers


def build_schedule(packets: Iterable[OverlayPacket], proposals: Iterable[OverlayProposal],
                   clock: PlayClock) -> ScheduleView:
    awaiting = sorted((p for p in proposals if p.status == ProposalStatus.PROPOSED), key=lambda p: p.priority)
    return ScheduleView(clock=clock.snapshot(), layers=_layers(list(packets), clock.play_ms),
                        awaiting_decision=awaiting)

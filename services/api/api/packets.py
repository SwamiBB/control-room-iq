"""Turning an operator decision into the OverlayPacket renderers and viewers receive.

Pure functions: no I/O, no clock reads, no model calls. The packet type itself is the gate, since it
cannot be constructed without approval fields, and these functions only ever build it from a logged
decision.
"""

from __future__ import annotations

from crq_schemas import (
    Access,
    Allegiance,
    DecisionLogEntry,
    FanCard,
    Lang,
    OverlayPacket,
    OverlayProposal,
    Persona,
)
from pydantic import BaseModel

from .clock import PlayClock

VERIFIED_FAITHFULNESS = 0.8


class ViewerPrefs(BaseModel):
    persona: Persona = Persona.FAN
    access: Access = "none"
    lang: Lang = "en"
    allegiance: Allegiance = "neutral"


# The v0.2 draft had persona=deaf; Viewer.tsx still sends it until the front end splits the picker.
_LEGACY_PERSONAS: dict[str, tuple[Persona, Access]] = {"deaf": (Persona.FAN, "deaf")}


def parse_viewer(persona: str, access: Access) -> tuple[Persona, Access]:
    """Raises ValueError for an unknown persona."""
    if persona in _LEGACY_PERSONAS:
        return _LEGACY_PERSONAS[persona]
    return Persona(persona), access


def cue_id_of(p: OverlayProposal) -> str:
    """The stable id the renderer upserts by."""
    return p.cue_id or f"c-{p.proposal_id}"


def slot_length_ms(p: OverlayProposal) -> int:
    """How long the graphic stays up: its proposed slot, never less than its minimum hold."""
    return max(p.t_end_ms - p.t_start_ms, p.min_hold_ms)


def packet_slot(p: OverlayProposal, now_play_ms: int) -> tuple[int, int]:
    """Play-time window for the packet.

    The scheduler (scheduler.py) places every proposal when it is fired, so this is its t_in/t_out. The
    fallback, for a proposal built without it: air now for its proposed duration, a package item its
    `package_offset_ms` later.
    """
    if p.t_out_ms > p.t_in_ms:
        return p.t_in_ms, p.t_out_ms
    start = now_play_ms + p.package_offset_ms
    return start, start + slot_length_ms(p)


def _is_verified(p: OverlayProposal) -> bool:
    # An operator's own words have not been through the faithfulness check (edit-with-re-verify is later).
    if p.override_line:
        return False
    return p.faithfulness is None or p.faithfulness >= VERIFIED_FAITHFULNESS


def build_packet(p: OverlayProposal, approval: DecisionLogEntry, clock: PlayClock) -> OverlayPacket:
    t_in, t_out = packet_slot(p, clock.play_ms)
    period, clock_ms = clock.display(t_in)
    return OverlayPacket(cue_id=cue_id_of(p), match_id=p.match_id, layer=p.layer,
                         t_in_ms=t_in, t_out_ms=t_out, period=period, clock_ms=clock_ms,
                         priority=p.priority, replaces=p.replaces, min_hold_ms=p.min_hold_ms,
                         line=p.override_line or p.line, payload=p.payload, verified=_is_verified(p),
                         # An override is the operator's own line, not the template's, whoever wrote the original.
                         fallback=p.fallback and not p.override_line, evidence=[e.event_id for e in p.evidence],
                         source_proposal_id=p.proposal_id, approval_id=approval.entry_id,
                         approved_by=approval.actor, approved_at=approval.at)


def attach_fan_card(packet: OverlayPacket, card: FanCard | None) -> OverlayPacket:
    return packet.model_copy(update={"fan_card": card}) if card else packet



def with_perspective(packet: OverlayPacket, framing: dict | None) -> OverlayPacket:
    """Adds supporter framing to the payload; the approved line is left exactly as it was."""
    if framing is None:
        return packet
    payload = packet.payload | {"perspective": framing}
    return packet.model_copy(update={"allegiance": framing["side"], "payload": payload})

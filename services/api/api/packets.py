"""Turning an operator decision into the OverlayPacket renderers and viewers receive.

Pure functions: no I/O, no clock reads, no model calls. The packet type itself is the gate, since it
cannot be constructed without approval fields, and these functions only ever build it from a logged
decision.
"""

from __future__ import annotations

from crq_schemas import (
    Access,
    DecisionLogEntry,
    FanCard,
    Lang,
    NarrativeVariant,
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
    club: str | None = None


# The v0.2 draft had persona=deaf; Viewer.tsx still sends it until the front end splits the picker.
_LEGACY_PERSONAS: dict[str, tuple[Persona, Access]] = {"deaf": (Persona.FAN, "deaf")}


def parse_viewer(persona: str, access: Access) -> tuple[Persona, Access]:
    """Raises ValueError for an unknown persona."""
    if persona in _LEGACY_PERSONAS:
        return _LEGACY_PERSONAS[persona]
    return Persona(persona), access


def packet_slot(p: OverlayProposal, now_play_ms: int) -> tuple[int, int]:
    """Play-time window for the packet.

    Uses the scheduler's t_in/t_out when it has placed the proposal. Until scheduler.py lands, an
    unplaced proposal airs now for its proposed duration; this is not collision-aware.
    """
    if p.t_out_ms > p.t_in_ms:
        return p.t_in_ms, p.t_out_ms
    duration = max(p.t_end_ms - p.t_start_ms, p.min_hold_ms)
    return now_play_ms, now_play_ms + duration


def _is_verified(p: OverlayProposal) -> bool:
    # An operator's own words have not been through the faithfulness check (edit-with-re-verify is later).
    if p.override_line:
        return False
    return p.faithfulness is None or p.faithfulness >= VERIFIED_FAITHFULNESS


def build_packet(p: OverlayProposal, approval: DecisionLogEntry, clock: PlayClock) -> OverlayPacket:
    t_in, t_out = packet_slot(p, clock.play_ms)
    period, clock_ms = clock.display(t_in)
    return OverlayPacket(cue_id=p.cue_id or f"c-{p.proposal_id}", match_id=p.match_id, layer=p.layer,
                         t_in_ms=t_in, t_out_ms=t_out, period=period, clock_ms=clock_ms,
                         priority=p.priority, replaces=p.replaces, min_hold_ms=p.min_hold_ms,
                         line=p.override_line or p.line, payload=p.payload, verified=_is_verified(p),
                         fallback=p.fallback, evidence=[e.event_id for e in p.evidence],
                         source_proposal_id=p.proposal_id, approval_id=approval.entry_id,
                         approved_by=approval.actor, approved_at=approval.at)


def attach_fan_card(packet: OverlayPacket, card: FanCard | None) -> OverlayPacket:
    return packet.model_copy(update={"fan_card": card}) if card else packet


def for_viewer(packet: OverlayPacket, variants: list[NarrativeVariant], prefs: ViewerPrefs) -> OverlayPacket:
    """The approved packet as one viewer sees it: their persona, access and language variant if one exists.

    Without an exact match the viewer gets the approved base line: a near match (say the hearing variant
    for a deaf viewer) could break the access rules. Callers pass no variants for an override, so the
    operator's line reaches everyone verbatim.
    """
    wanted = (prefs.persona, prefs.access, prefs.lang)
    v = next((v for v in variants if (v.persona, v.access, v.lang) == wanted), None)
    if v is None:
        return packet
    return packet.model_copy(update={"line": v.text, "profile": v.persona, "access": v.access, "lang": v.lang})

"""Decision timing: the warning before the SLA hold, and when a held graphic is too late to air.

Pure functions: no I/O and no clock reads. The SLA timer runs on wall-clock seconds (the operator's
time); shelf life runs on play time (the match's time), so a graphic about a moment expires once the
match has moved on, however fast a replay runs.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from crq_schemas import OverlayProposal, ProposalStatus

SLA_HOLD_S = 20.0  # no decision in this long: the SLA timer holds the graphic
SLA_WARN_S = 10.0  # the console starts warning this long before the hold
MIN_SHELF_LIFE_MS = 60_000  # a held graphic gets at least one minute of play to be fired

# Automated actors in the decision log. They may hold or expire a graphic, never air one.
SLA_ACTOR = "sla-timer"
EXPIRY_ACTOR = "expiry-rule"
SYSTEM_ACTORS = (SLA_ACTOR, EXPIRY_ACTOR)


def sla_times(proposed_at: datetime, hold_s: float = SLA_HOLD_S,
              warn_s: float = SLA_WARN_S) -> tuple[datetime, datetime]:
    """(warn_at, hold_at) for a proposal that reached the running order at `proposed_at`."""
    hold_at = proposed_at + timedelta(seconds=hold_s)
    return hold_at - timedelta(seconds=min(warn_s, hold_s)), hold_at


def shelf_life_ms(p: OverlayProposal) -> int:
    """How much play may pass before a held graphic is too late. The scheduler's max_delay, floored."""
    return max(p.max_delay_ms, MIN_SHELF_LIFE_MS)


def is_stale(p: OverlayProposal, now_play_ms: int) -> bool:
    """Only held graphics expire; one still awaiting a decision is the SLA timer's business first."""
    if p.status != ProposalStatus.HELD or p.proposed_play_ms is None:
        return False
    return now_play_ms - p.proposed_play_ms > shelf_life_ms(p)


def stale_proposals(proposals: Iterable[OverlayProposal], now_play_ms: int) -> list[OverlayProposal]:
    """Held graphics to expire, in running order. Items of one package share timing, so they go together."""
    stale = (p for p in proposals if is_stale(p, now_play_ms))
    return sorted(stale, key=lambda p: (p.package_id or "", p.package_seq))

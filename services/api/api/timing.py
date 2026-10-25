"""Decision timing: the warning before the SLA hold, and when a held graphic is too late to air.

Pure functions: no I/O and no clock reads — both clocks are passed in.

A held graphic expires only when *both* clocks say it is late. Play time says the match has moved
past the moment the graphic is about. Wall-clock time says the operator has actually had the graphic
on the desk long enough to act on it. Requiring both is what keeps a compressed replay honest: at
speed 20 the twenty wall-clock seconds the SLA gives an operator consume 400,000 ms of play, so a
play-time-only rule expires every held graphic the instant it is held and no human ever gets a turn.
The rule of thumb behind it: no deadline a human is expected to beat may be measured on a clock the
human does not control.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from crq_schemas import OverlayProposal, ProposalStatus

SLA_HOLD_S = 20.0  # no decision in this long: the SLA timer holds the graphic
SLA_WARN_S = 10.0  # the console starts warning this long before the hold
MIN_SHELF_LIFE_MS = 60_000  # play time: a held graphic gets at least one minute of match to be fired
MIN_SHELF_LIFE_WALL_S = 60.0  # wall time: and at least one real minute on the operator's desk

# Automated actors in the decision log. They may hold or expire a graphic, never air one.
SLA_ACTOR = "sla-timer"
EXPIRY_ACTOR = "expiry-rule"
SUPERSEDE_ACTOR = "supersession"  # a goal takes over every pending card from its move
SYSTEM_ACTORS = (SLA_ACTOR, EXPIRY_ACTOR, SUPERSEDE_ACTOR)


def sla_times(proposed_at: datetime, hold_s: float = SLA_HOLD_S,
              warn_s: float = SLA_WARN_S) -> tuple[datetime, datetime]:
    """(warn_at, hold_at) for a proposal that reached the running order at `proposed_at`."""
    hold_at = proposed_at + timedelta(seconds=hold_s)
    return hold_at - timedelta(seconds=min(warn_s, hold_s)), hold_at


def shelf_life_ms(p: OverlayProposal) -> int:
    """How much play may pass before a held graphic is too late. The scheduler's max_delay, floored."""
    return max(p.max_delay_ms, MIN_SHELF_LIFE_MS)


def is_stale(p: OverlayProposal, now_play_ms: int, now: datetime) -> bool:
    """Only held graphics expire; one still awaiting a decision is the SLA timer's business first.

    `now` is wall-clock time. A proposal with no `proposed_at` never reached the desk through the
    normal path, so there is no operator clock to measure and play time decides alone.
    """
    if p.status != ProposalStatus.HELD or p.proposed_play_ms is None:
        return False
    if now_play_ms - p.proposed_play_ms <= shelf_life_ms(p):
        return False
    if p.proposed_at is None:
        return True
    return (now - p.proposed_at).total_seconds() > MIN_SHELF_LIFE_WALL_S


def stale_proposals(proposals: Iterable[OverlayProposal], now_play_ms: int,
                    now: datetime) -> list[OverlayProposal]:
    """Held graphics to expire, in running order. Items of one package share timing, so they go together."""
    stale = (p for p in proposals if is_stale(p, now_play_ms, now))
    return sorted(stale, key=lambda p: (p.package_id or "", p.package_seq))

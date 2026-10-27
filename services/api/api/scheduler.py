"""Placement rules: when a fired graphic goes on air, for how long, and what it takes down (§6.3 of the design).

Code, not an agent: the same inputs always give the same placement, and every rule has a test. Pure functions of
the proposal, what is already on air or queued, the play clock and the moment. Called twice: when a card reaches
the desk (a provisional slot, so the running order shows where it would go) and again when it is fired, against
what is on air then.

The rules:
1. One graphic per layer at a time, in the earliest free gap that fits it.
2. One story at a time on the main layers: a graphic about a different moment starts at least 30 s after the last
   one began. The goal routine's own items and the ticker are exempt; a goal or red card is too.
3. A goal or a red card cuts what is on the lower third and the stat panel, so neither comes back after it.
4. The caption layer never queues: a new caption cuts the running one.
5. A graphic held back beyond its `max_delay_ms` cuts what blocks it when it outranks it (a lower priority
   number); otherwise it airs in its gap, marked late, because the operator chose to fire it.
6. Hold advice when pressure is rising and the moment is not a goal: a chance may be coming.
Every graphic stays up at least `min_hold_ms`; goal-routine items start their `package_offset_ms` after the fire.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from crq_schemas import HoldAdvice, Moment, MomentKind, OverlayLayer, OverlayPacket, OverlayProposal

STORY_GAP_MS = 30_000
MAIN_LAYERS = frozenset({OverlayLayer.LOWER_THIRD, OverlayLayer.STAT_PANEL, OverlayLayer.HEATMAP,
                         OverlayLayer.FULL_SCREEN})
CUT_BY_BIG_MOMENTS = frozenset({OverlayLayer.LOWER_THIRD, OverlayLayer.STAT_PANEL})
HOLD_ADVICE_MS = 20_000


@dataclass(frozen=True)
class Placement:
    t_in_ms: int
    t_out_ms: int
    replaces: list[str] = field(default_factory=list)
    late: bool = False  # aired past its max_delay_ms
    reason: str = ""  # why it isn't on at once, for the console and the trace


def is_big_moment(m: Moment | None) -> bool:
    """A goal, or a red card (a straight red or a second yellow): these cut the running lower third."""
    if m is None:
        return False
    return m.kind == MomentKind.GOAL or (m.kind == MomentKind.CARD
                                        and m.summary.startswith(("Red card", "Second yellow")))


def duration_ms(p: OverlayProposal) -> int:
    return max(p.t_end_ms - p.t_start_ms, p.min_hold_ms)


def _live(on_air: Iterable[OverlayPacket], now_ms: int) -> list[OverlayPacket]:
    """Packets still on air or queued: the latest per cue, without those a started packet has replaced."""
    latest: dict[str, OverlayPacket] = {}
    for pk in on_air:
        latest[pk.cue_id] = pk
    gone = {cue for pk in latest.values() if pk.t_in_ms <= now_ms for cue in pk.replaces}
    return [pk for pk in latest.values() if pk.cue_id not in gone and pk.t_out_ms > now_ms]


def _earliest_gap(busy: list[OverlayPacket], start: int, length: int) -> int:
    """The first start at or after `start` where [start, start + length) overlaps nothing on the layer."""
    for pk in sorted(busy, key=lambda pk: pk.t_in_ms):
        if pk.t_out_ms <= start or pk.t_in_ms >= start + length:
            continue
        start = pk.t_out_ms
    return start


def place(p: OverlayProposal, on_air: Iterable[OverlayPacket], now_ms: int, m: Moment | None,
          moment_of: Callable[[str], str | None] = lambda _proposal_id: None) -> Placement:
    """`moment_of` maps a packet's source proposal to its moment, so rule 2 can tell stories apart."""
    length = duration_ms(p)
    earliest = now_ms + p.package_offset_ms
    live = [pk for pk in _live(on_air, now_ms) if pk.source_proposal_id != p.proposal_id]
    own_cue = p.cue_id or f"c-{p.proposal_id}"

    if p.layer == OverlayLayer.CAPTION:  # never queues: the new caption cuts the running one
        cut = [pk.cue_id for pk in live if pk.layer == OverlayLayer.CAPTION and pk.cue_id != own_cue]
        return Placement(earliest, earliest + length, cut)

    if is_big_moment(m) and p.package_seq == 0:
        cut = [pk.cue_id for pk in live if pk.layer in CUT_BY_BIG_MOMENTS | {p.layer} and pk.cue_id != own_cue]
        return Placement(earliest, earliest + length, cut, reason="a goal or red card cuts the lower third")

    same_layer = [pk for pk in live if pk.layer == p.layer]
    start, reason = _earliest_gap(same_layer, earliest, length), ""
    if start > earliest:
        reason = f"waits for the {p.layer.value.replace('_', ' ')} to be free"

    if p.layer in MAIN_LAYERS and p.package_seq == 0:
        other_stories = [pk.t_in_ms for pk in live if pk.layer in MAIN_LAYERS
                         and moment_of(pk.source_proposal_id) not in (None, p.moment_id)]
        if other_stories and (gap_end := max(other_stories) + STORY_GAP_MS) > start:
            start = _earliest_gap(same_layer, gap_end, length)
            reason = "one story at a time: 30 s after the last one began"

    if start - earliest > p.max_delay_ms:
        blockers = [pk for pk in same_layer if pk.t_out_ms > earliest and pk.t_in_ms < earliest + length]
        if blockers and all(p.priority < pk.priority for pk in blockers):
            return Placement(earliest, earliest + length, [pk.cue_id for pk in blockers],
                             reason="outranks what was on the layer, so it cuts it")
        return Placement(start, start + length, late=True, reason=reason or "late")
    return Placement(start, start + length, reason=reason)


def hold_advice(m: Moment | None, now_ms: int) -> HoldAdvice:
    """Pressure rising and no goal yet: holding a few seconds may let the graphic tell the bigger story."""
    if m is None or m.kind == MomentKind.GOAL or m.state.pressure_trend != "rising":
        return HoldAdvice()
    return HoldAdvice(recommend_hold=True, reason="pressure is rising: a chance may follow, so holding may pay off",
                      until_play_ms=now_ms + HOLD_ADVICE_MS)

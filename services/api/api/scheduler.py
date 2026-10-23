"""LayerScheduler: which graphic goes on which layer, and when. Deterministic code, no model.

Rules (docs/SCHEMA_CHANGES.md section 5.5):
- no two items on one layer at once; a full screen also covers the lower third, stat panel and heat map;
- a new item takes the earliest free gap at or after its requested start;
- one story per window (60 s by default) across the story layers; ticker and badge are exempt;
- a goal or red card preempts: it airs now, cuts short whatever is running on the layers it covers, and
  pushes later queued items behind it;
- a held or superseded proposal gives its slot back.

Times are on one match clock in ms: period 1 is t_ms, period 2 is 60:00 + t_ms, so the halves never collide.
"""

from __future__ import annotations

from dataclasses import dataclass

from crq_schemas import MatchClock, OverlayLayer, OverlayProposal, ScheduledItem, ScreenState

PERIOD2_OFFSET_MS = 60 * 60 * 1000
DEFAULT_WINDOW_MS = 60_000
DEFAULT_DURATION_MS = 10_000
STORY_LAYERS = {OverlayLayer.FULL_SCREEN, OverlayLayer.LOWER_THIRD, OverlayLayer.STAT_PANEL, OverlayLayer.HEATMAP}
COVERS = {OverlayLayer.FULL_SCREEN: {OverlayLayer.LOWER_THIRD, OverlayLayer.STAT_PANEL, OverlayLayer.HEATMAP}}


def match_ms(period: int, t_ms: int) -> int:
    return t_ms + (PERIOD2_OFFSET_MS if period == 2 else 0)


def clock_of(ms: int) -> MatchClock:
    """Scheduler time back to the Opta-style match clock."""
    period = 2 if ms >= PERIOD2_OFFSET_MS else 1
    t = ms - (PERIOD2_OFFSET_MS if period == 2 else 0)
    return MatchClock(period=period, minute=t // 60000 + (45 if period == 2 else 0), second=(t // 1000) % 60)


def clashes(a: OverlayLayer, b: OverlayLayer) -> bool:
    return a == b or b in COVERS.get(a, set()) or a in COVERS.get(b, set())


@dataclass
class Booking:
    proposal_id: str
    layer: OverlayLayer
    start: int
    end: int
    window: int | None
    approved: bool = False

    def item(self) -> ScheduledItem:
        return ScheduledItem(proposal_id=self.proposal_id, layer=self.layer, t_start_ms=self.start, t_end_ms=self.end)


class LayerScheduler:
    def __init__(self, match_id: str, window_ms: int = DEFAULT_WINDOW_MS) -> None:
        self.match_id, self.window_ms = match_id, window_ms
        self.bookings: dict[str, Booking] = {}  # every slot ever given out, past ones included (the timeline)
        self.held: dict[str, Booking] = {}

    def _window(self, layer: OverlayLayer, start: int) -> int | None:
        return start // self.window_ms if layer in STORY_LAYERS else None

    def earliest(self, layer: OverlayLayer, desired: int, duration: int, ignore: str | None = None) -> int:
        others = [b for b in self.bookings.values() if b.proposal_id != ignore]
        t = desired
        while True:
            blockers = [b for b in others if clashes(b.layer, layer) and b.start < t + duration and t < b.end]
            if blockers:
                t = max(b.end for b in blockers)
                continue
            w = self._window(layer, t)
            if w is not None and any(b.window == w for b in others):
                t = (w + 1) * self.window_ms
                continue
            return t

    def _book(self, pid: str, layer: OverlayLayer, start: int, duration: int, approved: bool = False) -> Booking:
        b = Booking(pid, layer, start, start + duration, self._window(layer, start), approved)
        self.bookings[pid] = b
        return b

    def schedule(self, p: OverlayProposal, now_ms: int, preempts: bool = False) -> OverlayProposal:
        """Book a slot for a proposal (times already on the match clock) and return it with the slot filled in."""
        duration = p.t_end_ms - p.t_start_ms if p.t_end_ms > p.t_start_ms else DEFAULT_DURATION_MS
        desired = max(p.t_start_ms, now_ms)
        if preempts:
            start = desired
            for b in list(self.bookings.values()):
                if b.proposal_id == p.proposal_id or not clashes(b.layer, p.layer):
                    continue
                if b.start < start < b.end:
                    b.end = start  # cut short what is running
                elif start <= b.start < start + duration:
                    del self.bookings[b.proposal_id]  # queued behind: push it after the preempting item
                    self._book(b.proposal_id, b.layer, self.earliest(b.layer, start + duration, b.end - b.start),
                               b.end - b.start, b.approved)
        else:
            start = self.earliest(p.layer, desired, duration, ignore=p.proposal_id)
        b = self._book(p.proposal_id, p.layer, start, duration)
        return p.model_copy(update={"t_start_ms": b.start, "t_end_ms": b.end,
                                    "window_id": f"{self.match_id}-w{b.start // self.window_ms:04d}"})

    def approve(self, pid: str, now_ms: int) -> Booking | None:
        """Airing needs approval. Approved late (after its slot started) or out of hold: rebook from now."""
        b = self.bookings.get(pid) or self.held.pop(pid, None)
        if b is None:
            return None
        if b.start < now_ms or pid not in self.bookings:
            self.bookings.pop(pid, None)
            b = self._book(pid, b.layer, self.earliest(b.layer, now_ms, b.end - b.start, ignore=pid), b.end - b.start)
        b.approved = True
        return b

    def hold(self, pid: str) -> None:
        b = self.bookings.pop(pid, None)
        if b:
            self.held[pid] = b

    def release(self, pid: str) -> None:
        """Superseded or expired: the slot is free and nothing is kept."""
        self.bookings.pop(pid, None)
        self.held.pop(pid, None)

    def screen(self, now_ms: int) -> ScreenState:
        live = sorted(self.bookings.values(), key=lambda b: b.start)
        return ScreenState(match_id=self.match_id, t_ms=now_ms,
                           on_air=[b.item() for b in live if b.approved and b.start <= now_ms < b.end],
                           queued=[b.item() for b in live if b.end > now_ms and not (b.approved and b.start <= now_ms)],
                           held=[b.item() for b in self.held.values()])

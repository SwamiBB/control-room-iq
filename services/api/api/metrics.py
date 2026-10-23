"""Gallery metrics: turnaround, error rate and operator workload, from the decision log and deliveries.

Measure before scaling: these are the three numbers a broadcaster asks for before trusting an AI tool in
the gallery. Pure functions over records the API already keeps; no I/O and no clock reads.
"""

from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Iterable

from crq_schemas import DecisionLogEntry, OverlayProposal, ProposalStatus
from pydantic import BaseModel, Field

from .timing import EXPIRY_ACTOR, SLA_ACTOR, SYSTEM_ACTORS

FIRED = (ProposalStatus.APPROVED, ProposalStatus.OVERRIDDEN)
TEN_MINUTES_MS = 600_000


class Turnaround(BaseModel):
    """Seconds from a proposal reaching the running order to the operator firing it."""

    fired: int = 0
    median_s: float | None = None
    p90_s: float | None = None
    max_s: float | None = None


class ErrorRate(BaseModel):
    decided: int = 0
    overridden: int = 0
    dropped: int = Field(default=0, description="Rejected by the operator")
    override_rate: float | None = None
    drop_rate: float | None = None
    fallback_proposals: int = Field(default=0, description="Proposals built by the template fallback")
    deliveries: dict[str, int] = Field(default_factory=dict, description="variant / template / base / override")
    check_failures: dict[str, int] = Field(default_factory=dict, description="Variant check failure codes")


class Workload(BaseModel):
    operator_decisions: int = 0
    sla_holds: int = 0
    expired: int = Field(default=0, description="Held graphics the match moved past before anyone fired them")
    pending: int = 0
    play_minutes: float = 0.0
    decisions_per_10_min: float | None = None
    packages_fired: int = 0
    graphics_per_click: float | None = Field(default=None, description="Packets aired per operator decision")


class GalleryMetrics(BaseModel):
    turnaround: Turnaround
    errors: ErrorRate
    workload: Workload


def _action(e: DecisionLogEntry) -> str:
    return e.action.value if hasattr(e.action, "value") else str(e.action)


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 3) if d else None


def _p90(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.9 * (len(ordered) - 1)))]


def turnaround(proposals: dict[str, OverlayProposal], decisions: list[DecisionLogEntry]) -> Turnaround:
    seconds = []
    for e in decisions:
        p = proposals.get(e.proposal_id)
        if _action(e) in {a.value for a in FIRED} and p and p.proposed_at:
            seconds.append((e.at - p.proposed_at).total_seconds())
    if not seconds:
        return Turnaround()
    return Turnaround(fired=len(seconds), median_s=round(statistics.median(seconds), 2),
                      p90_s=round(_p90(seconds), 2), max_s=round(max(seconds), 2))


def errors(proposals: Iterable[OverlayProposal], decisions: list[DecisionLogEntry],
           deliveries: list[dict]) -> ErrorRate:
    by_action = Counter(_action(e) for e in decisions if e.actor not in SYSTEM_ACTORS)
    decided = sum(by_action[a] for a in ("approved", "overridden", "rejected"))
    failures = Counter(code for d in deliveries for code in d.get("failures", []))
    return ErrorRate(decided=decided, overridden=by_action["overridden"], dropped=by_action["rejected"],
                     override_rate=_rate(by_action["overridden"], decided),
                     drop_rate=_rate(by_action["rejected"], decided),
                     fallback_proposals=sum(1 for p in proposals if p.fallback),
                     deliveries=dict(Counter(d.get("source", "") for d in deliveries)), check_failures=dict(failures))


def workload(proposals: Iterable[OverlayProposal], decisions: list[DecisionLogEntry], play_ms: int,
             packets_aired: int) -> Workload:
    proposals = list(proposals)
    clicks = [e for e in decisions if e.actor not in SYSTEM_ACTORS]
    # One click on a package fires every item in it, and each item gets its own log row: count the click once.
    click_keys = {(e.package_id, _action(e)) if e.package_id else e.entry_id for e in clicks}
    fired_packages = {e.package_id for e in clicks if e.package_id and _action(e) in {a.value for a in FIRED}}
    minutes = play_ms / 60_000
    return Workload(operator_decisions=len(click_keys), sla_holds=sum(1 for e in decisions if e.actor == SLA_ACTOR),
                    expired=sum(1 for e in decisions if e.actor == EXPIRY_ACTOR),
                    pending=sum(1 for p in proposals if p.status in (ProposalStatus.PROPOSED, ProposalStatus.HELD)),
                    play_minutes=round(minutes, 1),
                    decisions_per_10_min=round(len(click_keys) / (play_ms / TEN_MINUTES_MS), 2) if play_ms else None,
                    packages_fired=len(fired_packages), graphics_per_click=_rate(packets_aired, len(click_keys)))


def gallery_metrics(proposals: dict[str, OverlayProposal], decisions: list[DecisionLogEntry],
                    deliveries: list[dict], play_ms: int, packets_aired: int) -> GalleryMetrics:
    return GalleryMetrics(turnaround=turnaround(proposals, decisions),
                          errors=errors(proposals.values(), decisions, deliveries),
                          workload=workload(proposals.values(), decisions, play_ms, packets_aired))

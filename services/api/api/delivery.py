"""Which text each viewer group receives once a proposal is approved.

Order of preference: a variant that passes every check, then a template line in the viewer's language,
then the approved base line (which stays marked as the base language). High-stakes moments use
templates outside the base language even when the variant passes, because one wrong word costs most there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from crq_schemas import Access, Lang, MomentKind, NarrativeVariant, OverlayPacket, Persona

from .packets import ViewerPrefs
from .variant_checks import BASE_LANG, CheckContext, check_variant

HIGH_STAKES_KINDS = frozenset({MomentKind.GOAL, MomentKind.CARD, MomentKind.STOPPAGE})

Source = Literal["variant", "template", "base", "override"]


@dataclass(frozen=True)
class DeliveryPlan:
    variants: tuple[NarrativeVariant, ...]
    ctx: CheckContext
    templates: dict[str, str]  # lang -> template line; empty when the moment kind has none
    is_high_stakes: bool
    is_override: bool
    # (persona, lang) -> that persona's own template line, preferred over the shared one (a goal's in Spanish and
    # Hindi, and the analyst's scorer stats)
    persona_templates: dict[tuple[Persona, str], str] = field(default_factory=dict)


@dataclass(frozen=True)
class Delivery:
    persona: Persona
    access: Access
    lang: Lang
    source: Source
    text: str | None
    failures: tuple[str, ...]

    def audit(self, packet: OverlayPacket) -> dict:
        return {"approval_id": packet.approval_id, "proposal_id": packet.source_proposal_id,
                "persona": self.persona.value, "access": self.access, "lang": self.lang, "source": self.source,
                "failures": list(self.failures)}


def _reasons(plan: DeliveryPlan, prefs: ViewerPrefs) -> tuple[NarrativeVariant | None, list[str]]:
    wanted = (prefs.persona, prefs.access, prefs.lang)
    v = next((v for v in plan.variants if (v.persona, v.access, v.lang) == wanted), None)
    reasons = check_variant(v, plan.ctx) if v else ["no_variant"]
    if plan.is_high_stakes and prefs.lang != BASE_LANG:
        reasons.append("high_stakes")
    return v, reasons


def choose_delivery(plan: DeliveryPlan, prefs: ViewerPrefs) -> Delivery:
    def delivery(source: Source, text: str | None, reasons: list[str]) -> Delivery:
        return Delivery(prefs.persona, prefs.access, prefs.lang, source, text, tuple(reasons))

    if plan.is_override:
        return delivery("override", None, [])
    v, reasons = _reasons(plan, prefs)
    if v is not None and not reasons:
        return delivery("variant", v.text, [])
    # A persona's own line first, in any language (the analyst's scorer stats have an English one too), then the
    # shared line in the viewer's language; English otherwise keeps the approved line.
    template = plan.persona_templates.get((prefs.persona, prefs.lang)) or (
        plan.templates.get(prefs.lang) if prefs.lang != BASE_LANG else None)
    return delivery("template", template, reasons) if template else delivery("base", None, reasons)


def apply_delivery(packet: OverlayPacket, d: Delivery) -> OverlayPacket:
    """Base and override keep the approved packet as-is, still marked as the base language."""
    if d.source in ("base", "override"):
        return packet
    update = {"line": d.text, "profile": d.persona, "access": d.access, "lang": d.lang}
    if d.source == "template":
        update["verified"] = True  # deterministic text from ground truth
    return packet.model_copy(update=update)

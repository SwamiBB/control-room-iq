"""Preview before firing: what each viewer group the graphics operator picks would see, and why.

The same delivery rules as airing (checked variant, then template, then the English line), run without
building a packet, logging a decision or sending anything. Nothing here can reach air.
Pure functions: no I/O, no clock reads, no model calls.
"""

from __future__ import annotations

from itertools import product
from typing import get_args

from crq_schemas import Access, Allegiance, Lang, MatchMeta, MatchState, OverlayProposal, Persona
from pydantic import BaseModel, Field

from .delivery import Delivery, DeliveryPlan, Source, choose_delivery
from .packets import ViewerPrefs, parse_viewer
from .perspective import perspective
from .variant_checks import BASE_LANG

DEFAULT_VIEW = ViewerPrefs()  # fan · no access mode · English · neutral, the viewer page's own defaults
MAX_VIEWS = 12


class ViewerGroup(BaseModel):
    """One option in the console's preview picker. `key` is what the preview route takes as `view`."""

    key: str
    persona: Persona
    access: Access
    lang: Lang
    allegiance: Allegiance


class PreviewItem(BaseModel):
    view: ViewerGroup
    source: Source = Field(description="variant / template / base / override, as it would air")
    text: str = Field(description="The line this viewer group would see")
    lang_shown: Lang = Field(description="Language of that text; the English line keeps 'en'")
    failures: list[str] = Field(default_factory=list, description="Why a variant would not air, if it would not")
    perspective: dict | None = Field(default=None, description="Supporter framing, for a home or away view")


class Preview(BaseModel):
    proposal_id: str
    override_line: str | None = None
    items: list[PreviewItem]


def view_key(prefs: ViewerPrefs) -> str:
    return ".".join((prefs.persona.value, prefs.access, prefs.lang, prefs.allegiance))


def parse_view(key: str) -> ViewerPrefs:
    """`persona.access.lang[.allegiance]`, e.g. `newcomer.none.hi.away`. Raises ValueError when unknown."""
    parts = key.split(".")
    if len(parts) not in (3, 4):
        raise ValueError(f"view must be persona.access.lang[.allegiance], got {key!r}")
    persona_raw, access, lang, *rest = parts
    allegiance = rest[0] if rest else "neutral"
    if access not in get_args(Access) or lang not in get_args(Lang) or allegiance not in get_args(Allegiance):
        raise ValueError(f"unknown access, language or side in {key!r}")
    persona, access_value = parse_viewer(persona_raw, access)  # type: ignore[arg-type]
    return ViewerPrefs(persona=persona, access=access_value, lang=lang, allegiance=allegiance)  # type: ignore[arg-type]


def viewer_groups(langs: tuple[str, ...]) -> list[ViewerGroup]:
    """Every option the picker can offer, in a stable order."""
    combos = product(Persona, get_args(Access), [lang for lang in get_args(Lang) if lang in langs],
                     get_args(Allegiance))
    return [_group(ViewerPrefs(persona=p, access=a, lang=lang, allegiance=s)) for p, a, lang, s in combos]


def _group(prefs: ViewerPrefs) -> ViewerGroup:
    return ViewerGroup(key=view_key(prefs), persona=prefs.persona, access=prefs.access, lang=prefs.lang,
                       allegiance=prefs.allegiance)


def _text(d: Delivery, p: OverlayProposal, override_line: str | None) -> tuple[str, str]:
    if d.source in ("variant", "template") and d.text:
        return d.text, d.lang
    return override_line or p.override_line or p.line, BASE_LANG


def preview(p: OverlayProposal, plan: DeliveryPlan, views: list[ViewerPrefs], state: MatchState | None,
            meta: MatchMeta | None, override_line: str | None = None) -> Preview:
    items = []
    for prefs in views:
        d = choose_delivery(plan, prefs)
        text, lang_shown = _text(d, p, override_line)
        framing = perspective(state, prefs, meta) if state else None
        items.append(PreviewItem(view=_group(prefs), source=d.source, text=text, lang_shown=lang_shown,  # type: ignore[arg-type]
                                 failures=list(d.failures), perspective=framing))
    return Preview(proposal_id=p.proposal_id, override_line=override_line, items=items)

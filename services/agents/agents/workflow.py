"""Moment -> Explanation -> Narrative -> English variants -> Spanish and Hindi, with the Producer alongside.

Five agents: explainer (why it matters), narrator (the English on-air line, and half/full-time recaps),
producer (the graphic and its evidence), personalizer (English versions per persona and access), and
localizer (Spanish and Hindi from the English versions, in one call). Placement, numbers, the strike cue
and the deaf fan's card are code, not agents.

Shared state is the `Moment` (which carries a MatchState snapshot) plus the proposal queue. Each
step has a timeout and a deterministic fallback so the pipeline always yields something the
operator can act on; failures are recorded in `MomentResult.failures` for the decision log.

Offline mode (CRQ_OFFLINE=1) runs fallbacks only, which makes the end-to-end demo runnable with no
Azure access and gives tests a stable baseline.

Match intelligence (speed and distance thresholds, pass quality, ball and shot speed) comes from the stats
engine via `match_intel`. Every agent receives it as `intel` (numbers + plain facts it may quote), and the
proposal's `payload.intel` is always set by code after the producer runs, so the graphic's numbers are ground
truth even when a model wrote the line.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import get_args

from crq_schemas import (
    Access,
    Explanation,
    MatchMeta,
    Moment,
    MomentKind,
    NarrativeVariant,
    OverlayLayer,
    OverlayProposal,
    Persona,
)

from .clients import make_agent
from .config import settings
from .match_intel import NameOf, intel_context, intel_for, intel_payload, intel_short

PROMPTS = Path(__file__).parent / "prompts"


def _prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


@dataclass
class MomentResult:
    moment: Moment
    explanation: Explanation
    line: str
    variants: list[NarrativeVariant]
    proposal: OverlayProposal | None
    failures: list[str] = field(default_factory=list)
    intel: dict | None = None  # the match-intelligence block the agents used (payload.intel shape)


# ---------- fallbacks (deterministic, template based) ----------

def fallback_explanation(m: Moment) -> Explanation:
    s = m.state
    pattern = {MomentKind.GOAL: "individual", MomentKind.BIG_CHANCE: "chaos",
               MomentKind.PRESSURE_SPIKE: "pressure_shift", MomentKind.MOMENTUM_SHIFT: "rhythm_change",
               MomentKind.SPEED_THRESHOLD: "individual", MomentKind.STANDOUT_PASS: "individual"}.get(m.kind, "control")
    why = (f"{m.summary}. Possession {s.home.possession_pct:.0f}-{s.away.possession_pct:.0f}, "
           f"xG {s.home.xg:.2f}-{s.away.xg:.2f}, score {s.home.goals}-{s.away.goals}.")
    short = intel_short(intel_for(m), _prefer(m))
    if short:
        why = f"{why} Match intelligence: {short}."
    return Explanation(moment_id=m.moment_id, headline=m.summary[:60], why_it_matters=why, pattern=pattern,  # type: ignore[arg-type]
                       cites=list(m.event_ids), confidence=0.5)


def fallback_line(m: Moment, e: Explanation) -> str:
    return e.headline


VariantRequest = tuple[Persona, Access, str, dict]  # persona, access, lang, focus


INTEL_KINDS = frozenset({MomentKind.SPEED_THRESHOLD, MomentKind.STANDOUT_PASS})


def _fallback_text(m: Moment, line: str, persona: Persona, access: Access) -> str:
    s = m.state
    text = line
    short = intel_short(intel_for(m), _prefer(m))
    if persona == Persona.ANALYST:
        # On a speed or pass moment the analyst's number is the intel; elsewhere it is xG and possession.
        if short and m.kind in INTEL_KINDS:
            text = line if _says_already(line, short) else f"{line} ({short})"
        else:
            text = f"{line} (xG {s.home.xg:.2f}-{s.away.xg:.2f}, possession {s.home.possession_pct:.0f}%)"
    if access == "deaf":
        text = f"{text}. The score is {s.home.goals} to {s.away.goals}."
    return text


BASE_LANG = "en"


def fallback_variants(m: Moment, line: str, requests: list[VariantRequest]) -> list[NarrativeVariant]:
    """English only. The fallback never writes Spanish or Hindi: English text labeled as another language would
    be a lie, so those viewers get the API's template line (or the approved English line) instead (#17)."""
    return [NarrativeVariant(moment_id=m.moment_id, persona=persona, access=access, lang=lang,  # type: ignore[arg-type]
                             text=_fallback_text(m, line, persona, access), cites=list(m.event_ids))
            for persona, access, lang, _focus in requests if lang == BASE_LANG]


def english_requests(requests: list[VariantRequest]) -> list[VariantRequest]:
    """The English versions the personalizer must write: one per persona and access asked for in any language."""
    seen: dict[tuple, VariantRequest] = {}
    for persona, access, _lang, focus in requests:
        seen.setdefault((persona, access), (persona, access, BASE_LANG, focus))
    return list(seen.values())


def localize_targets(requests: list[VariantRequest]) -> list[tuple[Persona, Access, str]]:
    return list(dict.fromkeys((p, a, lang) for p, a, lang, _f in requests if lang != BASE_LANG))


def keep_localized(raw: list[NarrativeVariant], english: list[NarrativeVariant],
                   targets: list[tuple[Persona, Access, str]]) -> list[NarrativeVariant]:
    """Code, not trust: keep only requested non-English versions with an English source, one per target, and
    give each the cites of its English source (the localizer translates; it does not re-cite)."""
    source = {(v.persona, v.access): v for v in english}
    wanted = set(targets)
    out: dict[tuple, NarrativeVariant] = {}
    for v in raw:
        key = (v.persona, v.access, v.lang)
        src = source.get((v.persona, v.access))
        if key in wanted and src is not None and key not in out:
            out[key] = v.model_copy(update={"cites": list(src.cites), "moment_id": src.moment_id})
    return list(out.values())


def _parse_variants(res, err: str | None, label: str, fallback) -> tuple[list[NarrativeVariant], str | None]:
    if isinstance(res, str):
        try:
            return [NarrativeVariant.model_validate(v) for v in json.loads(res)], err
        except Exception as ex:  # noqa: BLE001
            return fallback(), err or f"{label}: bad JSON: {ex}"
    return res, err


def priority_from_importance(importance: float) -> int:
    """Map a 0-1 importance score onto the 1-9 priority rank (1 = highest); 0.5 lands on the default of 5."""
    return 1 + round((1 - importance) * 8)


def fallback_proposal(m: Moment, e: Explanation, line: str) -> OverlayProposal | None:
    if m.importance < 0.35:
        return None
    layer = {MomentKind.GOAL: OverlayLayer.FULL_SCREEN, MomentKind.HALF_END: OverlayLayer.FULL_SCREEN,
             MomentKind.MATCH_END: OverlayLayer.FULL_SCREEN, MomentKind.PRESSURE_SPIKE: OverlayLayer.HEATMAP,
             MomentKind.MOMENTUM_SHIFT: OverlayLayer.STAT_PANEL,
             MomentKind.STANDOUT_PASS: OverlayLayer.STAT_PANEL}.get(m.kind, OverlayLayer.LOWER_THIRD)
    dur = {OverlayLayer.FULL_SCREEN: 18000, OverlayLayer.STAT_PANEL: 15000,
           OverlayLayer.HEATMAP: 15000}.get(layer, 10000)
    s = m.state
    payload = {"score": [s.home.goals, s.away.goals], "xg": [s.home.xg, s.away.xg],
               "possession": [s.home.possession_pct, s.away.possession_pct], "momentum": s.momentum[-10:]}
    intel = intel_payload(intel_for(m), _prefer(m))
    if intel:
        payload["intel"] = intel
    reasoning = f"Template fallback: {m.kind.value} with importance {m.importance} maps to {layer.value}."
    return OverlayProposal(proposal_id="p-" + uuid.uuid4().hex[:8], match_id=m.match_id, moment_id=m.moment_id,
                           layer=layer, t_start_ms=m.t_ms + 2000, t_end_ms=m.t_ms + 2000 + dur, line=line,
                           payload=payload, reasoning=reasoning,
                           priority=priority_from_importance(m.importance))


# ---------- agents ----------

async def _run(agent, payload: dict, model, fallback):
    if agent is None:
        return fallback(), None
    try:
        res = await asyncio.wait_for(agent.run(json.dumps(payload, default=str)), timeout=settings.agent_timeout_s)
        text = getattr(res, "text", None) or str(res)
        return (model.model_validate_json(text) if model else text.strip()), None
    except Exception as ex:  # noqa: BLE001 - any failure falls back; recorded for the decision log
        return fallback(), f"{getattr(agent, 'name', 'agent')}: {type(ex).__name__}: {ex}"


class MomentPipeline:
    def __init__(self) -> None:
        self.explainer = make_agent("explainer", _prompt("explainer"), Explanation)
        self.narrator = make_agent("narrator", _prompt("narrator"))
        self.personalizer = make_agent("personalizer", _prompt("personalizer"))
        self.localizer = make_agent("localizer", _prompt("localizer"))
        self.producer = make_agent("producer", _prompt("producer"), OverlayProposal)

    async def process(self, m: Moment, on_air: list[dict] | None = None,
                      requests: list[VariantRequest] | None = None, meta: MatchMeta | None = None) -> MomentResult:
        requests = requests or [(p, a, lang, {})
                                for p in Persona for a in get_args(Access) for lang in settings.languages]
        failures: list[str] = []
        moment_json = json.loads(m.model_dump_json())
        intel = intel_context(m, _name_of(meta))

        expl, err = await _run(self.explainer, {"moment": moment_json, "intel": intel}, Explanation,
                               lambda: fallback_explanation(m))
        if err:
            failures.append(err)
        line, err = await _run(self.narrator, {"moment": moment_json, "explanation": expl.model_dump(),
                                               "intel": intel}, None, lambda: fallback_line(m, expl))
        if err:
            failures.append(err)

        # The producer runs alongside the personalizer -> localizer chain once the line exists.
        en_requests = english_requests(requests)
        targets = localize_targets(requests)

        async def _variants():
            wanted = [{"persona": p.value, "access": a, "lang": lang, "focus": f} for p, a, lang, f in en_requests]
            raw, e1 = await _run(self.personalizer, {"line": line, "moment": moment_json, "intel": intel,
                                                     "requests": wanted},
                                 None, lambda: fallback_variants(m, line, en_requests))
            english, e1 = _parse_variants(raw, e1, "personalizer", lambda: fallback_variants(m, line, en_requests))
            english = [v for v in english if v.lang == BASE_LANG]
            if not targets:
                return english, [e1]
            want = [{"persona": p.value, "access": a, "lang": lang} for p, a, lang in targets]
            source = [v.model_dump(mode="json") for v in english]
            raw, e2 = await _run(self.localizer, {"line": line, "variants": source, "moment": moment_json,
                                                  "intel": intel, "names": _names(meta), "targets": want}, None, list)
            localized, e2 = _parse_variants(raw, e2, "localizer", list)
            return english + keep_localized(localized, english, targets), [e1, e2]

        async def _proposal():
            return await _run(self.producer, {"moment": moment_json, "explanation": expl.model_dump(), "line": line,
                                              "intel": intel, "on_air": on_air or []}, OverlayProposal,
                              lambda: fallback_proposal(m, expl, line))

        (variants, variant_errors), (proposal, e3) = await asyncio.gather(_variants(), _proposal())
        proposal = with_intel(proposal, m, _name_of(meta))
        failures += [e for e in (*variant_errors, e3) if e]
        return MomentResult(moment=m, explanation=expl, line=line, variants=variants, proposal=proposal,
                            failures=failures, intel=intel_payload(intel_for(m), _prefer(m), _name_of(meta)))


def with_intel(proposal: OverlayProposal | None, m: Moment, name_of: NameOf | None = None) -> OverlayProposal | None:
    """Numbers from code: whatever the producer wrote, `payload.intel` is the stats engine's ground truth."""
    if proposal is None:
        return None
    intel = intel_payload(intel_for(m), _prefer(m), name_of)
    payload = {k: v for k, v in proposal.payload.items() if k != "intel"}
    if intel:
        payload["intel"] = intel
    return proposal.model_copy(update={"payload": payload})


def _says_already(line: str, clause: str) -> bool:
    """True when the line already quotes the clause's lead number, compared as values ('32.0' equals '32')."""
    nums = re.findall(r"\d+(?:\.\d+)?", clause)
    return bool(nums) and float(nums[0]) in {float(n) for n in re.findall(r"\d+(?:\.\d+)?", line)}


def _prefer(m: Moment) -> str | None:
    return "pass" if m.kind == MomentKind.STANDOUT_PASS else None


def _names(meta: MatchMeta | None) -> list[str]:
    """Player and club names the localizer must keep exactly as written."""
    if meta is None:
        return []
    return [t.name for t in (meta.home, meta.away)] + [p.name for t in (meta.home, meta.away) for p in t.players]


def _name_of(meta: MatchMeta | None) -> NameOf:
    names = {p.player_id: p.name for t in (meta.home, meta.away) for p in t.players} if meta else {}
    return lambda pid: names.get(pid or "", pid or "")

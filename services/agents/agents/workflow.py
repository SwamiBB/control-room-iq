"""Moment -> Explanation -> Narrative -> Producer (the card) -> English variants -> Spanish and Hindi.

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
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, get_args

from crq_schemas import (
    Access,
    AgentMeta,
    Alternative,
    Explanation,
    Lang,
    MatchMeta,
    Moment,
    MomentKind,
    NarrativeVariant,
    OverlayLayer,
    OverlayProposal,
    Persona,
    max_chars_for,
)
from pydantic import BaseModel, Field

from .clients import make_agent
from .config import AGENT_ROUTING, settings
from .match_intel import NameOf, intel_context, intel_for, intel_payload, intel_short
from .telemetry import brief, tracer

logger = logging.getLogger(__name__)

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
    # Decisions worth showing that are not failures, e.g. the producer choosing no graphic for a moment.
    notes: list[str] = field(default_factory=list)


# Receives the card as soon as the producer has written it: a MomentResult with no variants yet.
OnCard = Callable[[MomentResult], Awaitable[None]]


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


def _parse_variants(res, err: str | None, label: str, fallback, moment_id: str,
                    meta: AgentMeta) -> tuple[list[NarrativeVariant], str | None]:
    """A model reply is held to its VariantsOut schema; the moment id and run details come from code."""
    if isinstance(res, str):
        try:
            out = VariantsOut.model_validate_json(res)
        except Exception as ex:  # noqa: BLE001
            return fallback(), err or f"{label}: bad JSON: {ex}"
        return [NarrativeVariant(moment_id=moment_id, meta=meta, **v.model_dump()) for v in out.variants], err
    return res, err


def priority_from_importance(importance: float) -> int:
    """Map a 0-1 importance score onto the 1-9 priority rank (1 = highest); 0.5 lands on the default of 5."""
    return 1 + round((1 - importance) * 8)


class VariantOut(BaseModel):
    persona: Persona
    access: Access
    lang: Lang
    text: str
    cites: list[str]


class VariantsOut(BaseModel):
    """Personalizer and localizer output. Structured, because free-form JSON dropped required fields live."""
    variants: list[VariantOut]


class ExplanationOut(BaseModel):
    """What the explainer model writes; the moment id and the run details (meta) are set by code."""
    headline: str
    why_it_matters: str
    pattern: Literal["control", "chaos", "pressure_shift", "rhythm_change", "individual", "set_piece"]
    cites: list[str]
    confidence: float = Field(ge=0, le=1)


# The layers the producer may choose; caption, player_tag and pitch_overlay are filled by code only.
ProducerLayer = Literal["lower_third", "stat_panel", "heatmap", "ticker", "full_screen"]


class ProducerAlternative(BaseModel):
    layer: ProducerLayer
    line: str
    rejected_because: str


class ProducerDecision(BaseModel):
    """What the producer model writes. Strict structured output rejects free-form objects, so the renderer
    payload travels as a JSON string; ids, status and approval fields are set by code, not invented (#33)."""
    propose: bool = Field(description="False when the moment does not deserve a graphic")
    layer: ProducerLayer
    t_start_ms: int
    t_end_ms: int
    line: str
    payload_json: str = Field(description="JSON object with the renderer's fields for this layer")
    reasoning: str
    alternatives: list[ProducerAlternative]


# Code decides whether a moment gets a graphic: below this importance never (ordinary stoppages sit at 0.32 on
# purpose, so they reach the deaf fan but not the operator queue), and these kinds always.
MIN_PROPOSAL_IMPORTANCE = 0.35
ALWAYS_PROPOSE = frozenset({MomentKind.GOAL, MomentKind.HALF_END, MomentKind.MATCH_END})


def wants_proposal(m: Moment) -> bool:
    return m.kind in ALWAYS_PROPOSE or m.importance >= MIN_PROPOSAL_IMPORTANCE


def model_meta(info: dict, agent: str) -> AgentMeta:
    """Run details for a model-written output: the agent's routing mode (its router deployment, #47), the model
    the router served, and the latency."""
    return AgentMeta(routing=AGENT_ROUTING.get(agent, "balanced"), model_served=info.get("model_served"),
                     latency_ms=info.get("latency_ms"))


# The longest slot the producer may give each layer (the prompt's ranges; ticker and heatmap by analogy). Viewers
# hold a graphic for its slot in real time, so an over-long slot would sit on screen for minutes.
MAX_SLOT_MS = {"lower_third": 12_000, "stat_panel": 20_000, "heatmap": 20_000, "ticker": 30_000,
               "full_screen": 25_000}


def proposal_from(d: ProducerDecision, m: Moment, meta: AgentMeta) -> tuple[OverlayProposal, str | None]:
    """The proposal, and an error when the payload had to be dropped (it is never silently emptied).

    A slot longer than its layer allows is shortened to the maximum, not rejected: the graphic is still good."""
    err = None
    t_end_ms = min(d.t_end_ms, d.t_start_ms + MAX_SLOT_MS[d.layer])
    try:
        payload = json.loads(d.payload_json)
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        payload, err = {}, "producer: payload_json is not a JSON object; the graphic has no payload"
    alternatives = [Alternative(layer=OverlayLayer(a.layer), line=a.line, rejected_because=a.rejected_because)
                    for a in d.alternatives]
    return OverlayProposal(proposal_id="p-" + uuid.uuid4().hex[:8], match_id=m.match_id, moment_id=m.moment_id,
                           layer=OverlayLayer(d.layer), t_start_ms=d.t_start_ms, t_end_ms=t_end_ms, line=d.line,
                           payload=payload, reasoning=d.reasoning, alternatives=alternatives, meta=meta,
                           priority=priority_from_importance(m.importance)), err


def fallback_proposal(m: Moment, e: Explanation, line: str) -> OverlayProposal | None:
    if not wants_proposal(m):
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
                           payload=payload, reasoning=reasoning, fallback=True,
                           priority=priority_from_importance(m.importance))


# ---------- agents ----------

async def _run(agent, payload: dict, model, fallback, info: dict | None = None):
    """`info`, when given, receives the call's latency_ms and the model the router served.

    Each call is a `crq.agent <role>` span in the moment's trace: its routing mode, the model the router chose, and
    whether the call itself failed and why. A reply rejected later (bad JSON, a declined goal) is a template
    fallback too: the moment's span lists them all. Agent Framework's spans (tokens, the request) nest inside."""
    if agent is None:
        return fallback(), None
    role = getattr(agent, "name", "agent")
    seen: dict = {} if info is None else info
    with tracer.start_as_current_span(f"crq.agent {role}", attributes={
            "crq.agent": role, "crq.routing": AGENT_ROUTING.get(role, "balanced")}) as span:
        try:
            result, error = await _call(agent, payload, model, fallback, seen)
        except asyncio.CancelledError:
            span.set_attribute("crq.cancelled", True)  # a new match replaced this one mid-call
            raise
        span.set_attribute("crq.call_failed", error is not None)
        if error:
            span.set_attribute("crq.error", brief(error))
        for key in ("model_served", "latency_ms"):
            if seen.get(key) is not None:
                span.set_attribute(f"crq.{key}", seen[key])
        return result, error


async def _call(agent, payload: dict, model, fallback, info: dict):
    try:
        started = time.perf_counter()
        res = await asyncio.wait_for(agent.run(json.dumps(payload, default=str)), timeout=settings.agent_timeout_s)
        info["latency_ms"] = round((time.perf_counter() - started) * 1000)
        info["model_served"] = getattr(getattr(res, "raw_representation", None), "model", None)
        text = getattr(res, "text", None) or str(res)
        return (model.model_validate_json(text) if model else text.strip()), None
    except Exception as ex:  # noqa: BLE001 - any failure falls back; recorded for the decision log
        name = getattr(agent, "name", "agent")
        # A timeout has an empty message, which left only "TimeoutError: " in the decision log (#39).
        reason = (f"timed out after {settings.agent_timeout_s:g} s" if isinstance(ex, TimeoutError)
                  else f"{type(ex).__name__}: {ex}")
        logger.warning("Agent %s fell back to its template: %s", name, brief(reason))  # logs go to App Insights
        return fallback(), f"{name}: {reason}"


class MomentPipeline:
    def __init__(self) -> None:
        self.explainer = make_agent("explainer", _prompt("explainer"), ExplanationOut)
        self.narrator = make_agent("narrator", _prompt("narrator"))
        self.personalizer = make_agent("personalizer", _prompt("personalizer"), VariantsOut)
        self.localizer = make_agent("localizer", _prompt("localizer"), VariantsOut)
        self.producer = make_agent("producer", _prompt("producer"), ProducerDecision)

    @classmethod
    def templates_only(cls) -> MomentPipeline:
        """The same pipeline with no model calls: every agent uses its template (the daily budget is spent)."""
        p = cls.__new__(cls)
        p.explainer = p.narrator = p.personalizer = p.localizer = p.producer = None
        return p

    async def process(self, m: Moment, on_air: list[dict] | None = None,
                      requests: list[VariantRequest] | None = None, meta: MatchMeta | None = None,
                      on_card: OnCard | None = None) -> MomentResult:
        """Run the agents on one moment.

        The producer writes the card right after the narrator, and `on_card` receives it at once (a result with
        no variants yet), so the operator isn't kept waiting for translations. The personalizer and localizer
        then write every version from the **card's** line and within its layer's length: the line that airs is
        the line every viewer's version is checked against (#90).
        """
        requests = requests or [(p, a, lang, {})
                                for p in Persona for a in get_args(Access) for lang in settings.languages]
        failures: list[str] = []
        moment_json = json.loads(m.model_dump_json())
        intel = intel_context(m, _name_of(meta))

        info: dict = {}
        teams = _teams(meta)
        out, err = await _run(self.explainer, {"moment": moment_json, "intel": intel, "teams": teams}, ExplanationOut,
                              lambda: None, info)
        if out is None:
            expl = fallback_explanation(m)
        else:
            expl = Explanation(moment_id=m.moment_id, **out.model_dump(), meta=model_meta(info, "explainer"))
        if err:
            failures.append(err)
        expl = expl.model_copy(update={"headline": club_names(expl.headline, meta),
                                       "why_it_matters": club_names(expl.why_it_matters, meta)})
        line, err = await _run(self.narrator, {"moment": moment_json, "explanation": expl.model_dump(),
                                               "intel": intel, "teams": teams}, None, lambda: fallback_line(m, expl))
        line = club_names(line, meta)
        if err:
            failures.append(err)

        en_requests = english_requests(requests)
        targets = localize_targets(requests)

        async def _variants(source_line: str, max_chars: int | None):
            wanted = [{"persona": p.value, "access": a, "lang": lang, "focus": f} for p, a, lang, f in en_requests]
            info1: dict = {}
            raw, e1 = await _run(self.personalizer, {"line": source_line, "max_chars": max_chars,
                                                     "moment": moment_json, "intel": intel, "requests": wanted},
                                 None, lambda: fallback_variants(m, source_line, en_requests), info1)
            english, e1 = _parse_variants(raw, e1, "personalizer",
                                          lambda: fallback_variants(m, source_line, en_requests),
                                          m.moment_id, model_meta(info1, "personalizer"))
            first: dict[tuple, NarrativeVariant] = {}
            for v in english:
                if v.lang == BASE_LANG:
                    first.setdefault((v.persona, v.access), v)
            english = list(first.values())
            if missing := [r for r in en_requests if (r[0], r[1]) not in first]:
                english += fallback_variants(m, source_line, missing)
                e1 = e1 or f"personalizer: {len(missing)} of {len(en_requests)} versions missing; templates used"
            if not targets:
                return english, [e1]
            want = [{"persona": p.value, "access": a, "lang": lang} for p, a, lang in targets]
            source = [v.model_dump(mode="json") for v in english]
            info2: dict = {}
            raw, e2 = await _run(self.localizer, {"line": source_line, "max_chars": max_chars, "variants": source,
                                                  "moment": moment_json, "intel": intel, "names": _names(meta),
                                                  "targets": want}, None, list, info2)
            localized, e2 = _parse_variants(raw, e2, "localizer", list, m.moment_id, model_meta(info2, "localizer"))
            kept = keep_localized(localized, english, targets)
            if self.localizer is not None and not e2 and len(kept) < len(targets):
                e2 = f"localizer: {len(kept)} of {len(targets)} versions; the rest get the template line"
            return english + kept, [e1, e2]

        notes: list[str] = []

        async def _proposal():
            if not wants_proposal(m):
                return None, None
            info3: dict = {}
            decision, err = await _run(self.producer, {"moment": moment_json, "explanation": expl.model_dump(),
                                                       "line": line, "intel": intel, "teams": teams,
                                                       "on_air": on_air or []},
                                       ProducerDecision, lambda: None, info3)
            if decision is None:
                return fallback_proposal(m, expl, line), err
            if not decision.propose:
                if m.kind in ALWAYS_PROPOSE:
                    return fallback_proposal(m, expl, line), f"producer: declined a {m.kind.value}; template used"
                # A deliberate "no graphic" is the producer's call, not a failure.
                # Operator-readable: the console shows notes as written (#41).
                notes.append(f"No graphic proposed: {decision.reasoning}")
                return None, None
            if decision.t_end_ms <= decision.t_start_ms:
                return fallback_proposal(m, expl, line), "producer: t_end_ms is not after t_start_ms; template used"
            return proposal_from(decision, m, model_meta(info3, "producer"))

        proposal, e3 = await _proposal()
        proposal = with_intel(proposal, m, _name_of(meta))
        written = proposal.line if proposal is not None else ""
        if proposal is not None:
            alternatives = [a.model_copy(update={"line": club_names(a.line, meta)}) for a in proposal.alternatives]
            proposal = proposal.model_copy(update={"line": club_names(proposal.line, meta),
                                                   "alternatives": alternatives})
        if e3:
            failures.append(e3)
        moment_intel = intel_payload(intel_for(m), _prefer(m), _name_of(meta))
        if on_card is not None:
            await on_card(MomentResult(moment=m, explanation=expl, line=line, variants=[], proposal=proposal,
                                       failures=list(failures), intel=moment_intel, notes=list(notes)))
        if proposal is None:  # no card, so nothing airs from this moment: no versions to write
            return MomentResult(moment=m, explanation=expl, line=line, variants=[], proposal=None,
                                failures=failures, intel=moment_intel, notes=notes)
        # Every version is written from the line that airs, to fit its graphic.
        # The budget is the card as it was written to fit: a code expanded to a club name mustn't widen it for every
        # version. A version pushed over it by its own expansion fails the length check and gets the template.
        variants, variant_errors = await _variants(proposal.line, max_chars_for(proposal.layer, written))
        variants = [v.model_copy(update={"text": club_names(v.text, meta)}) for v in variants]
        failures += [e for e in variant_errors if e]
        return MomentResult(moment=m, explanation=expl, line=line, variants=variants, proposal=proposal,
                            failures=failures, intel=moment_intel, notes=notes)


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


def _teams(meta: MatchMeta | None) -> dict[str, str]:
    """Team id -> club name, so the agents can name clubs the way viewers know them (#40)."""
    return {t.team_id: t.name for t in (meta.home, meta.away)} if meta else {}


def club_names(text: str, meta: MatchMeta | None) -> str:
    """A team id or code an agent wrote anyway ("puts har ahead", "HAR lead") becomes the club's name, so the line
    airs as viewers know it and every language agrees on the name (#40).

    One pass over whole words, full club names first, so a club already named is left alone even when its code is
    also one of its words ("Inter Milan" stays). Codes match in any case, since the agents wrote "Har" and "Nfu";
    a club whose code is an ordinary word ("BAR", "NEW") would also change that word."""
    if not meta:
        return text
    teams = (meta.home, meta.away)
    names = {t.name.lower(): t.name for t in teams}
    codes = {c.lower(): t.name for t in teams for c in (t.team_id, t.short_name)}
    words = sorted({*names, *codes}, key=len, reverse=True)
    pattern = rf"(?<!\w)(?:{'|'.join(map(re.escape, words))})(?!\w)"
    # A function, not a replacement string: a club name is never read as a regex template.
    return re.sub(pattern, lambda w: w[0] if w[0].lower() in names else codes[w[0].lower()], text, flags=re.IGNORECASE)


def _name_of(meta: MatchMeta | None) -> NameOf:
    names = {p.player_id: p.name for t in (meta.home, meta.away) for p in t.players} if meta else {}
    return lambda pid: names.get(pid or "", pid or "")

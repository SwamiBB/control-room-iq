"""Moment -> Explanation -> Narrative -> Variants, with the Producer running alongside.

Shared state is the `Moment` (which carries a MatchState snapshot) plus the proposal queue. Each
step has a timeout and a deterministic fallback so the pipeline always yields something the
operator can act on; failures are recorded in `MomentResult.failures` for the decision log.

Offline mode (CRQ_OFFLINE=1) runs fallbacks only, which makes the end-to-end demo runnable with no
Azure access and gives tests a stable baseline.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from crq_schemas import (Explanation, Moment, MomentKind, NarrativeVariant, OverlayLayer, OverlayProposal,
                         Persona)

from .clients import make_agent
from .config import settings

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


# ---------- fallbacks (deterministic, template based) ----------

def fallback_explanation(m: Moment) -> Explanation:
    s = m.state
    pattern = {MomentKind.GOAL: "individual", MomentKind.BIG_CHANCE: "chaos", MomentKind.PRESSURE_SPIKE: "pressure_shift",
               MomentKind.MOMENTUM_SHIFT: "rhythm_change", MomentKind.SPEED_THRESHOLD: "individual"}.get(m.kind, "control")
    why = (f"{m.summary}. Possession {s.home.possession_pct:.0f}-{s.away.possession_pct:.0f}, "
           f"xG {s.home.xg:.2f}-{s.away.xg:.2f}, score {s.home.goals}-{s.away.goals}.")
    return Explanation(moment_id=m.moment_id, headline=m.summary[:60], why_it_matters=why, pattern=pattern,  # type: ignore[arg-type]
                       cites=list(m.event_ids), confidence=0.5)


def fallback_line(m: Moment, e: Explanation) -> str:
    return e.headline


def fallback_variants(m: Moment, line: str, requests: list[tuple[Persona, str, dict]]) -> list[NarrativeVariant]:
    s = m.state
    out = []
    for persona, lang, _focus in requests:
        text = line
        if persona == Persona.ANALYST:
            text = f"{line} (xG {s.home.xg:.2f}-{s.away.xg:.2f}, possession {s.home.possession_pct:.0f}%)"
        elif persona == Persona.DEAF:
            text = f"{line}. The score is {s.home.goals} to {s.away.goals}."
        out.append(NarrativeVariant(moment_id=m.moment_id, persona=persona, lang=lang, text=text, cites=list(m.event_ids)))  # type: ignore[arg-type]
    return out


def priority_from_importance(importance: float) -> int:
    """Map a 0-1 importance score onto the 1-9 priority rank (1 = highest); 0.5 lands on the default of 5."""
    return 1 + round((1 - importance) * 8)


def fallback_proposal(m: Moment, e: Explanation, line: str) -> OverlayProposal | None:
    if m.importance < 0.35:
        return None
    layer = {MomentKind.GOAL: OverlayLayer.FULL_SCREEN, MomentKind.HALF_END: OverlayLayer.FULL_SCREEN,
             MomentKind.MATCH_END: OverlayLayer.FULL_SCREEN, MomentKind.PRESSURE_SPIKE: OverlayLayer.HEATMAP,
             MomentKind.MOMENTUM_SHIFT: OverlayLayer.STAT_PANEL}.get(m.kind, OverlayLayer.LOWER_THIRD)
    dur = {OverlayLayer.FULL_SCREEN: 18000, OverlayLayer.STAT_PANEL: 15000, OverlayLayer.HEATMAP: 15000}.get(layer, 10000)
    s = m.state
    return OverlayProposal(proposal_id="p-" + uuid.uuid4().hex[:8], match_id=m.match_id, moment_id=m.moment_id, layer=layer,
                           t_start_ms=m.t_ms + 2000, t_end_ms=m.t_ms + 2000 + dur, line=line,
                           payload={"score": [s.home.goals, s.away.goals], "xg": [s.home.xg, s.away.xg],
                                    "possession": [s.home.possession_pct, s.away.possession_pct], "momentum": s.momentum[-10:]},
                           reasoning=f"Template fallback: {m.kind.value} with importance {m.importance} maps to {layer.value}.",
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
        self.producer = make_agent("producer", _prompt("producer"), OverlayProposal)

    async def process(self, m: Moment, on_air: list[dict] | None = None,
                      requests: list[tuple[Persona, str, dict]] | None = None) -> MomentResult:
        requests = requests or [(p, lang, {}) for p in Persona for lang in settings.languages]
        failures: list[str] = []
        moment_json = json.loads(m.model_dump_json())

        expl, err = await _run(self.explainer, {"moment": moment_json}, Explanation, lambda: fallback_explanation(m))
        if err:
            failures.append(err)
        line, err = await _run(self.narrator, {"moment": moment_json, "explanation": expl.model_dump()}, None,
                               lambda: fallback_line(m, expl))
        if err:
            failures.append(err)

        # personalizer and producer are independent once the line exists -> run concurrently
        async def _variants():
            res, e = await _run(self.personalizer, {"line": line, "moment": moment_json,
                                                    "requests": [{"persona": p.value, "lang": l, "focus": f} for p, l, f in requests]},
                                None, lambda: fallback_variants(m, line, requests))
            if isinstance(res, str):
                try:
                    res = [NarrativeVariant.model_validate(v) for v in json.loads(res)]
                except Exception as ex:  # noqa: BLE001
                    e = e or f"personalizer: bad JSON: {ex}"
                    res = fallback_variants(m, line, requests)
            return res, e

        async def _proposal():
            return await _run(self.producer, {"moment": moment_json, "explanation": expl.model_dump(), "line": line,
                                              "on_air": on_air or []}, OverlayProposal,
                              lambda: fallback_proposal(m, expl, line))

        (variants, e1), (proposal, e2) = await asyncio.gather(_variants(), _proposal())
        failures += [e for e in (e1, e2) if e]
        return MomentResult(moment=m, explanation=expl, line=line, variants=variants, proposal=proposal, failures=failures)

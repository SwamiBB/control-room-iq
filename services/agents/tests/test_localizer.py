"""The localizer: Spanish and Hindi from the personalizer's English versions, checked and trimmed in code."""

import os

os.environ["CRQ_OFFLINE"] = "1"

import asyncio  # noqa: E402
import json  # noqa: E402

from agents.config import deployment_for, settings  # noqa: E402
from agents.workflow import (  # noqa: E402
    MomentPipeline,
    ProducerDecision,
    english_requests,
    fallback_explanation,
    fallback_proposal,
    fallback_variants,
    keep_localized,
    localize_targets,
)
from crq_schemas import MomentKind, NarrativeVariant, Persona, TeamStats  # noqa: E402
from simulator.cli import build_meta  # noqa: E402

META = build_meta(42)


def _decision(p):
    """The producer's reply shape (#33), built from a template proposal."""
    return ProducerDecision(propose=True, layer=p.layer, t_start_ms=p.t_start_ms, t_end_ms=p.t_end_ms, line=p.line,
                            payload_json=json.dumps(p.payload), reasoning=p.reasoning,
                            alternatives=[]).model_dump_json()


def _moment():
    from crq_schemas import MatchState, Moment
    state = MatchState(match_id="m", seq=1, period=1, t_ms=600_000, home=TeamStats(team="har", goals=1),
                       away=TeamStats(team="nfu"))
    return Moment(moment_id="mo-1", match_id="m", t_ms=600_000, period=1, kind=MomentKind.BIG_CHANCE,
                  importance=0.7, team="har", player="har-09", event_ids=["e-1", "e-2"], summary="Big chance",
                  state=state)


def _v(persona: str, access: str, lang: str, text: str, cites=None) -> NarrativeVariant:
    return NarrativeVariant(moment_id="mo-1", persona=persona, access=access, lang=lang, text=text,
                            cites=cites if cites is not None else ["e-1"])


def _reply(*variants: NarrativeVariant) -> str:
    """A personalizer or localizer reply in its VariantsOut shape."""
    return json.dumps({"variants": [v.model_dump(mode="json", include={"persona", "access", "lang", "text", "cites"})
                                    for v in variants]})


class _Agent:
    def __init__(self, reply: str, name: str = "agent") -> None:
        self.reply, self.inputs, self.name = reply, [], name

    async def run(self, text: str):
        self.inputs.append(json.loads(text))
        return type("R", (), {"text": self.reply})()


REQUESTS = [(Persona.FAN, "none", "en", {}), (Persona.FAN, "none", "es", {}), (Persona.FAN, "deaf", "hi", {})]


def test_personalizer_writes_english_once_per_persona_and_access():
    assert english_requests(REQUESTS) == [(Persona.FAN, "none", "en", {}), (Persona.FAN, "deaf", "en", {})]
    assert localize_targets(REQUESTS) == [(Persona.FAN, "none", "es"), (Persona.FAN, "deaf", "hi")]


def test_fallback_never_labels_english_as_another_language():
    variants = fallback_variants(_moment(), "Big chance", REQUESTS)
    assert {v.lang for v in variants} == {"en"}


def test_keep_localized_takes_requested_targets_and_the_english_cites():
    english = [_v("fan", "none", "en", "Big chance", ["e-1", "e-2"]), _v("fan", "deaf", "en", "Big chance. 1-0")]
    raw = [_v("fan", "none", "es", "Gran ocasión", cites=["made-up"]),
           _v("fan", "none", "es", "Duplicado"),            # second answer for the same target: dropped
           _v("fan", "none", "en", "Big chance"),           # English is not the localizer's job: dropped
           _v("analyst", "none", "es", "No pedido"),        # not requested, no English source: dropped
           _v("fan", "deaf", "hi", "बड़ा मौका। 1-0")]
    kept = keep_localized(raw, english, [(Persona.FAN, "none", "es"), (Persona.FAN, "deaf", "hi")])
    assert [(v.lang, v.text, v.cites) for v in kept] == [("es", "Gran ocasión", ["e-1", "e-2"]),
                                                          ("hi", "बड़ा मौका। 1-0", ["e-1"])]


def _pipeline(personalizer_reply: str, localizer_reply: str) -> MomentPipeline:
    m = _moment()
    p = MomentPipeline()
    p.explainer = _Agent(fallback_explanation(m).model_dump_json())
    p.narrator = _Agent("Big chance for Harbor City")
    p.personalizer = _Agent(personalizer_reply)
    p.localizer = _Agent(localizer_reply, name="localizer")
    p.producer = _Agent(_decision(fallback_proposal(m, fallback_explanation(m), "x")))
    return p


def test_localizer_gets_the_english_versions_names_and_targets_and_its_output_is_kept():
    english = _reply(_v("fan", "none", "en", "Big chance for Harbor City"),
                     _v("fan", "deaf", "en", "Big chance for Harbor City. 1-0"))
    localized = _reply(_v("fan", "none", "es", "Gran ocasión para Harbor City"),
                       _v("fan", "deaf", "hi", "Harbor City का बड़ा मौका। 1-0"))
    p = _pipeline(english, localized)
    res = asyncio.run(p.process(_moment(), requests=REQUESTS, meta=META))
    sent = p.localizer.inputs[0]
    assert [v["lang"] for v in sent["variants"]] == ["en", "en"]
    assert sent["targets"] == [{"persona": "fan", "access": "none", "lang": "es"},
                               {"persona": "fan", "access": "deaf", "lang": "hi"}]
    assert "Harbor City" in sent["names"] and META.home.players[0].name in sent["names"]
    assert {(v.access, v.lang) for v in res.variants} == {("none", "en"), ("deaf", "en"), ("none", "es"),
                                                         ("deaf", "hi")}
    assert res.failures == []


def test_a_broken_localizer_reply_leaves_english_only_and_is_logged():
    english = _reply(_v("fan", "none", "en", "Big chance"), _v("fan", "deaf", "en", "Big chance. 1-0"))
    res = asyncio.run(_pipeline(english, "not json").process(_moment(), requests=REQUESTS, meta=META))
    assert {v.lang for v in res.variants} == {"en"}
    assert any(f.startswith("localizer: bad JSON") for f in res.failures)


def test_no_non_english_request_means_no_localizer_call():
    english = _reply(_v("fan", "none", "en", "Big chance"))
    p = _pipeline(english, _reply())
    asyncio.run(p.process(_moment(), requests=[(Persona.FAN, "none", "en", {})], meta=META))
    assert p.localizer.inputs == []


def test_each_agent_has_a_router_deployment():
    assert deployment_for("explainer") == settings.router_quality == deployment_for("producer")
    assert deployment_for("narrator") == settings.router_balanced
    assert deployment_for("personalizer") == settings.router_cost == deployment_for("localizer")
    assert deployment_for("unknown") == settings.model_router

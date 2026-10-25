"""Code, not the model, owns the decisions around each agent's output: whether a moment gets a graphic, which
layers the producer may use, ids and run details, and what happens when a reply is short or malformed."""

import os

os.environ["CRQ_OFFLINE"] = "1"

import asyncio  # noqa: E402
import json  # noqa: E402
from typing import get_args  # noqa: E402

import pytest  # noqa: E402
from agents.workflow import (  # noqa: E402
    MomentPipeline,
    ProducerDecision,
    ProducerLayer,
    fallback_explanation,
    fallback_proposal,
)
from crq_schemas import MatchState, Moment, MomentKind, Persona, TeamStats  # noqa: E402
from pydantic import ValidationError  # noqa: E402

FAN_EN = [(Persona.FAN, "none", "en", {}), (Persona.FAN, "deaf", "en", {})]


def _moment(kind=MomentKind.BIG_CHANCE, importance=0.7) -> Moment:
    state = MatchState(match_id="m", seq=1, period=1, t_ms=600_000, home=TeamStats(team="har", goals=1),
                       away=TeamStats(team="nfu"))
    return Moment(moment_id="mo-1", match_id="m", t_ms=600_000, period=1, kind=kind, importance=importance,
                  team="har", event_ids=["e-1"], summary="Big chance", state=state)


class _Agent:
    def __init__(self, reply: str, name: str = "agent") -> None:
        self.reply, self.calls, self.name = reply, 0, name

    async def run(self, text: str):
        self.calls += 1
        return type("R", (), {"text": self.reply, "raw_representation": type("C", (), {"model": "test-model"})()})()


def _decision(**overrides) -> str:
    fields = {"propose": True, "layer": "lower_third", "t_start_ms": 602_000, "t_end_ms": 612_000,
              "line": "Big chance for Harbor City", "payload_json": json.dumps({"label": "Big chance"}),
              "reasoning": "A clear chance.", "alternatives": []}
    return json.dumps({**fields, **overrides})


def _variants(*pairs: tuple[str, str]) -> str:
    return json.dumps({"variants": [{"persona": p, "access": a, "lang": "en", "text": f"{p} {a}", "cites": ["e-1"]}
                                    for p, a in pairs]})


def _pipeline(producer: str = "", personalizer: str | None = None,
              explainer: str | None = None) -> MomentPipeline:
    p = MomentPipeline()
    p.explainer = _Agent(explainer or fallback_explanation(_moment()).model_dump_json(), "explainer")
    p.narrator = _Agent("Big chance for Harbor City", "narrator")
    p.personalizer = _Agent(personalizer or _variants(("fan", "none"), ("fan", "deaf")), "personalizer")
    p.localizer = _Agent('{"variants": []}', "localizer")
    p.producer = _Agent(producer or _decision(), "producer")
    return p


def _run(p: MomentPipeline, m: Moment):
    return asyncio.run(p.process(m, requests=FAN_EN))


def test_template_proposals_are_flagged_as_fallback():
    assert fallback_proposal(_moment(), fallback_explanation(_moment()), "x").fallback is True


def test_below_the_proposal_floor_the_producer_is_not_asked():
    p = _pipeline()
    res = _run(p, _moment(kind=MomentKind.STOPPAGE, importance=0.32))
    assert res.proposal is None and p.producer.calls == 0 and res.failures == []


def test_a_declined_goal_still_gets_the_template_proposal():
    res = _run(_pipeline(_decision(propose=False)), _moment(kind=MomentKind.GOAL, importance=1.0))
    assert res.proposal is not None and res.proposal.fallback is True
    assert any("declined a goal" in f for f in res.failures)


def test_a_declined_ordinary_moment_is_a_note_not_a_failure():
    res = _run(_pipeline(_decision(propose=False)), _moment())
    assert res.proposal is None and res.failures == []
    assert res.notes == ["producer: no graphic for big_chance (importance 0.7): A clear chance."]


def test_a_low_importance_goal_still_asks_the_producer_and_keeps_its_graphic():
    p = _pipeline(_decision(propose=False))
    res = _run(p, _moment(kind=MomentKind.GOAL, importance=0.2))
    assert p.producer.calls == 1 and res.proposal is not None and res.proposal.fallback is True


def test_a_proposal_that_ends_before_it_starts_uses_the_template():
    res = _run(_pipeline(_decision(t_end_ms=600_000)), _moment())
    assert res.proposal is not None and res.proposal.fallback is True
    assert any("t_end_ms is not after t_start_ms" in f for f in res.failures)


def test_model_outputs_carry_their_run_details_and_templates_do_not():
    res = _run(_pipeline(personalizer=_variants(("fan", "none"))), _moment())
    assert res.proposal.meta.routing == "balanced" and res.proposal.meta.model_served == "test-model"
    by_access = {v.access: v for v in res.variants}
    assert by_access["none"].meta.model_served == "test-model"
    assert by_access["deaf"].meta.routing == "template"  # filled from the template, not the model


def test_a_short_localizer_reply_is_logged():
    p = _pipeline()
    p.localizer = _Agent(json.dumps({"variants": [{"persona": "fan", "access": "none", "lang": "es",
                                                   "text": "Gran ocasión", "cites": []}]}), "localizer")
    res = asyncio.run(p.process(_moment(), requests=FAN_EN + [(Persona.FAN, "none", "es", {}),
                                                              (Persona.FAN, "deaf", "hi", {})]))
    assert {(v.access, v.lang) for v in res.variants if v.lang != "en"} == {("none", "es")}
    assert any(f == "localizer: 1 of 2 versions; the rest get the template line" for f in res.failures)


def test_the_producer_may_only_use_its_five_layers():
    assert set(get_args(ProducerLayer)) == {"lower_third", "stat_panel", "heatmap", "ticker", "full_screen"}
    with pytest.raises(ValidationError):
        ProducerDecision.model_validate_json(_decision(layer="caption"))
    res = _run(_pipeline(_decision(layer="caption")), _moment())
    assert res.proposal is not None and res.proposal.fallback is True  # rejected reply -> template, logged
    assert any(f.startswith("producer:") for f in res.failures)


def test_a_bad_payload_is_dropped_and_logged():
    res = _run(_pipeline(_decision(payload_json="not json")), _moment())
    assert res.proposal is not None and res.proposal.fallback is False
    assert "label" not in res.proposal.payload
    assert any("payload_json is not a JSON object" in f for f in res.failures)


def test_a_model_proposal_is_built_by_code():
    res = _run(_pipeline(), _moment())
    p = res.proposal
    assert p is not None and p.fallback is False and p.moment_id == "mo-1" and p.proposal_id.startswith("p-")
    assert p.payload["label"] == "Big chance" and p.status.value == "proposed"


def test_the_explainer_gets_its_moment_id_and_run_details_from_code():
    reply = json.dumps({"moment_id": "invented", "headline": "h", "why_it_matters": "w", "pattern": "chaos",
                        "cites": ["e-1"], "confidence": 0.8, "meta": {"routing": "quality", "latency_ms": 1}})
    expl = _run(_pipeline(explainer=reply), _moment()).explanation
    assert expl.moment_id == "mo-1"
    assert expl.meta.routing == "balanced" and expl.meta.model_served == "test-model"
    assert expl.meta.latency_ms is not None and expl.meta.latency_ms != 1


def test_variants_take_the_moment_id_from_code():
    res = _run(_pipeline(), _moment())
    assert {v.moment_id for v in res.variants} == {"mo-1"}


def test_missing_personalizer_versions_get_templates_and_are_logged():
    res = _run(_pipeline(personalizer=_variants(("fan", "none"))), _moment())
    assert {(v.access, v.lang) for v in res.variants} == {("none", "en"), ("deaf", "en")}
    deaf = next(v for v in res.variants if v.access == "deaf")
    assert deaf.text.endswith("The score is 1 to 0.")  # the template, not the model
    assert any("1 of 2 versions missing" in f for f in res.failures)


def test_an_empty_personalizer_reply_falls_back_for_every_version():
    res = _run(_pipeline(personalizer='{"variants": []}'), _moment())
    assert len(res.variants) == 2
    assert any("2 of 2 versions missing" in f for f in res.failures)


def test_a_bare_list_reply_is_not_accepted():
    res = _run(_pipeline(personalizer=json.dumps([{"persona": "fan", "access": "none", "lang": "en",
                                                    "text": "x", "cites": []}])), _moment())
    assert any(f.startswith("personalizer: bad JSON") for f in res.failures)

"""#90: the card is handed over before the translations, and every version is written from the card's line."""

import os

os.environ["CRQ_OFFLINE"] = "1"

import asyncio  # noqa: E402
import json  # noqa: E402

from agents.workflow import MomentPipeline, fallback_explanation  # noqa: E402
from crq_schemas import LAYER_MAX_CHARS, MatchState, Moment, MomentKind, OverlayLayer, Persona, TeamStats  # noqa: E402

REQUESTS = [(Persona.FAN, "none", "en", {}), (Persona.FAN, "none", "es", {})]
CARD_LINE = "Kai Reed denied from close range"


def _moment() -> Moment:
    state = MatchState(match_id="m", seq=1, period=1, t_ms=600_000, home=TeamStats(team="har"),
                       away=TeamStats(team="nfu"))
    return Moment(moment_id="mo-1", match_id="m", t_ms=600_000, period=1, kind=MomentKind.BIG_CHANCE,
                  importance=0.7, team="har", event_ids=["e-1"], summary="Big chance", state=state)


class _Agent:
    """Records what it was sent, and when, relative to the other agents."""

    def __init__(self, reply: str, name: str, log: list) -> None:
        self.reply, self.name, self.log, self.inputs = reply, name, log, []

    async def run(self, text: str):
        self.inputs.append(json.loads(text))
        self.log.append(self.name)
        return type("R", (), {"text": self.reply, "raw_representation": type("C", (), {"model": "m"})()})()


def _pipeline(log: list) -> MomentPipeline:
    p = MomentPipeline()
    p.explainer = _Agent(fallback_explanation(_moment()).model_dump_json(), "explainer", log)
    p.narrator = _Agent("Kai Reed sees his shot from close range saved after a long spell of home pressure",
                        "narrator", log)
    p.producer = _Agent(json.dumps({"propose": True, "layer": "lower_third", "t_start_ms": 602_000,
                                    "t_end_ms": 612_000, "line": CARD_LINE, "payload_json": "{}",
                                    "reasoning": "A clear chance.", "alternatives": []}), "producer", log)
    p.personalizer = _Agent(json.dumps({"variants": [{"persona": "fan", "access": "none", "lang": "en",
                                                      "text": "Kai Reed denied!", "cites": []}]}),
                            "personalizer", log)
    p.localizer = _Agent(json.dumps({"variants": [{"persona": "fan", "access": "none", "lang": "es",
                                                   "text": "¡Kai Reed, negado!", "cites": []}]}), "localizer", log)
    return p


def test_the_card_is_handed_over_before_the_translations_are_written():
    log: list = []
    handed: list = []

    async def on_card(card):
        handed.append((list(log), card))

    p = _pipeline(log)
    res = asyncio.run(p.process(_moment(), requests=REQUESTS, on_card=on_card))
    (seen_by_then, card), = handed
    assert seen_by_then == ["explainer", "narrator", "producer"]  # nothing translated yet
    assert card.proposal is not None and card.proposal.line == CARD_LINE and card.variants == []
    assert log == ["explainer", "narrator", "producer", "personalizer", "localizer"]
    assert {v.lang for v in res.variants} == {"en", "es"}  # the full result still carries every version


def test_versions_are_written_from_the_card_line_within_its_layer():
    log: list = []
    p = _pipeline(log)
    asyncio.run(p.process(_moment(), requests=REQUESTS))
    for agent in (p.personalizer, p.localizer):
        sent = agent.inputs[0]
        assert sent["line"] == CARD_LINE  # not the narrator's longer sentence
        assert sent["max_chars"] == LAYER_MAX_CHARS[OverlayLayer.LOWER_THIRD]


def test_without_a_card_no_versions_are_written():
    log: list = []
    p = _pipeline(log)
    p.producer.reply = json.dumps({"propose": False, "layer": "lower_third", "t_start_ms": 1, "t_end_ms": 2,
                                   "line": "", "payload_json": "{}", "reasoning": "Nothing to show.",
                                   "alternatives": []})
    handed: list = []

    async def on_card(card):
        handed.append(card)

    res = asyncio.run(p.process(_moment(), requests=REQUESTS, on_card=on_card))
    assert handed[0].proposal is None
    assert log == ["explainer", "narrator", "producer"]  # nothing airs, so nothing is translated
    assert res.variants == [] and res.proposal is None


def test_a_fallback_card_over_its_layer_limit_sets_the_limit():
    log: list = []
    p = _pipeline(log)
    long_line = "Kai Reed sees his shot from close range saved after a long, long spell of sustained home pressure"
    assert len(long_line) > LAYER_MAX_CHARS[OverlayLayer.LOWER_THIRD]
    p.narrator.reply = long_line
    p.producer.reply = "not json"  # the producer fails: the template card carries the narrator's line
    res = asyncio.run(p.process(_moment(), requests=REQUESTS))
    assert res.proposal is not None and res.proposal.fallback and res.proposal.line == long_line
    assert p.personalizer.inputs[0]["max_chars"] == len(long_line)  # a version need not be shorter than its source


def test_each_agent_call_is_a_span_with_its_routing_and_the_model_served(spans):
    log: list = []
    p = _pipeline(log)

    class Broken(_Agent):
        async def run(self, text: str):
            raise ConnectionError("router unreachable")

    p.narrator = Broken("", "narrator", log)  # the narrator's call fails: its span says it fell back, and why
    asyncio.run(p.process(_moment(), requests=REQUESTS))
    by_agent = {s.attributes["crq.agent"]: s for s in spans.get_finished_spans() if s.name.startswith("crq.agent ")}
    assert set(by_agent) == {"explainer", "narrator", "producer", "personalizer", "localizer"}
    assert by_agent["producer"].attributes["crq.routing"] == "quality"
    assert by_agent["producer"].attributes["crq.model_served"] == "m"
    assert not by_agent["producer"].attributes["crq.call_failed"]
    narrator = by_agent["narrator"].attributes
    # Trace content is off in the tests: the error's type is kept, its message (which can quote a reply) is not.
    assert narrator["crq.call_failed"] and narrator["crq.error"] == "narrator: ConnectionError"

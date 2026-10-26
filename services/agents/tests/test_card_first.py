"""#90: the card is handed over before the translations, and every version is written from the card's line."""

import os

os.environ["CRQ_OFFLINE"] = "1"

import asyncio  # noqa: E402
import json  # noqa: E402

from agents.workflow import LAYER_MAX_CHARS, MomentPipeline, fallback_explanation  # noqa: E402
from crq_schemas import MatchState, Moment, MomentKind, OverlayLayer, Persona, TeamStats  # noqa: E402

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


def test_without_a_card_the_narrator_line_is_the_source_and_there_is_no_limit():
    log: list = []
    p = _pipeline(log)
    p.producer.reply = json.dumps({"propose": False, "layer": "lower_third", "t_start_ms": 1, "t_end_ms": 2,
                                   "line": "", "payload_json": "{}", "reasoning": "Nothing to show.",
                                   "alternatives": []})
    handed: list = []

    async def on_card(card):
        handed.append(card)

    asyncio.run(p.process(_moment(), requests=REQUESTS, on_card=on_card))
    assert handed[0].proposal is None
    assert p.personalizer.inputs[0]["line"].startswith("Kai Reed sees his shot")
    assert p.personalizer.inputs[0]["max_chars"] is None

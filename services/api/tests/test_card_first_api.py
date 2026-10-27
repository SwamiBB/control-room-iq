"""#90: the API puts the card on the desk when the producer hands it over, before the translations arrive."""

import asyncio

import api.main as main
from agents.workflow import MomentResult, fallback_explanation
from api.main import _handle_moment, hub
from api_factories import moment, proposal


def _result(m, p, variants=()):
    return MomentResult(moment=m, explanation=fallback_explanation(m), line="l", variants=list(variants),
                        proposal=p, failures=[])


def test_the_card_is_queued_while_the_translations_are_still_being_written(monkeypatch):
    hub.auto_hold_s = 3600
    m = moment()
    card = proposal("p-early")
    released = asyncio.Event()
    seen_while_waiting: dict = {}

    async def process(_m, on_card=None, **_kwargs):
        await on_card(_result(m, card))
        seen_while_waiting["queued"] = "p-early" in hub.proposals
        seen_while_waiting["record"] = m.moment_id in hub.results
        await released.wait()  # the personalizer and localizer still writing
        return _result(m, card)

    async def run():
        task = asyncio.create_task(_handle_moment(m))
        await asyncio.sleep(0)
        released.set()
        await task

    monkeypatch.setattr(main.pipeline, "process", process)
    asyncio.run(run())
    assert seen_while_waiting == {"queued": True, "record": True}
    assert list(hub.proposals).count("p-early") == 1  # queued once, not again when the result arrives


def test_a_goal_that_arrived_first_keeps_the_card_off_the_desk(monkeypatch):
    m = moment()
    card = proposal("p-late")
    monkeypatch.setattr(main, "_taken_by_goal", lambda _m: True)

    async def process(_m, on_card=None, **_kwargs):
        await on_card(_result(m, card))
        return _result(m, card)

    monkeypatch.setattr(main.pipeline, "process", process)
    asyncio.run(_handle_moment(m))
    assert "p-late" not in hub.proposals
    assert main.GOAL_TOOK_OVER in hub.results[m.moment_id]["notes"]


def test_an_error_queueing_the_card_fails_the_moment_rather_than_skipping_the_translations(monkeypatch):
    m = moment()
    translated = []

    async def broken_queue(_p, _m):
        raise ValueError("the goal package could not be built")

    async def process(_m, on_card=None, **_kwargs):
        await on_card(_result(m, proposal("p-x")))
        translated.append(True)
        return _result(m, proposal("p-x"))

    monkeypatch.setattr(main, "_queue_card", broken_queue)
    monkeypatch.setattr(main.pipeline, "process", process)
    try:
        asyncio.run(_handle_moment(m))
    except ValueError as e:
        assert "goal package" in str(e)  # the real error, not "versions failed after the card"
    else:
        raise AssertionError("a queueing error must not be swallowed")
    assert translated == []


# ---- unsourced_numbers: AI check only, not for template fallbacks or code-built lines -----------------

def _queue_sync(p):
    """Run _queue_card and return the queued lead proposal from the hub."""
    from api.main import _queue_card
    hub.proposals.clear()
    m = moment()
    asyncio.run(_queue_card(p, m))
    return next(iter(hub.proposals.values()))


def test_template_fallback_line_is_not_flagged_as_unsourced():
    """A template line's numbers are authored in fallback_text.py; flagging them would be a false positive."""
    p = proposal("p-tpl", line="Big chance Kai Reed saved (xG 0.678)", fallback=True)
    lead = _queue_sync(p)
    assert lead.unsourced_numbers == []  # 0.678 is not in the moment state, but a template is trustworthy


def test_code_built_line_is_not_flagged_as_unsourced():
    """A code-built line (speed milestone, scorer stats, package item) comes from our own code."""
    from crq_schemas import AgentMeta
    p = proposal("p-code", line="Ade Pike hits 32.1 km/h",
                 meta=AgentMeta(routing="template", model_served=None, latency_ms=None))
    lead = _queue_sync(p)
    assert lead.unsourced_numbers == []


def test_model_authored_line_is_still_checked():
    """When a router deployment produced the line, unsourced numbers must still be flagged."""
    from crq_schemas import AgentMeta
    p = proposal("p-ai", line="Kai Reed denied, xG 0.42",
                 meta=AgentMeta(routing="quality", model_served="gpt-5.6-sol-2026-07-09", latency_ms=1200))
    lead = _queue_sync(p)
    assert "0.42" in lead.unsourced_numbers  # the AI invented this number, flag it

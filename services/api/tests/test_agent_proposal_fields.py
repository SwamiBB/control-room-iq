"""The producer agent proposes content; fields the API owns are never taken from its output."""

import asyncio
from types import SimpleNamespace

import api.main as main
from agents.workflow import fallback_explanation
from api.main import _handle_moment, hub
from api_factories import moment, proposal
from crq_schemas import ProposalStatus


def test_api_owned_fields_from_the_agent_are_reset_on_arrival(monkeypatch):
    hub.auto_hold_s = 3600  # keep the SLA timer out of this test
    hub.proposals["p-goal"] = proposal("p-goal", package_id="pk-p-goal")
    m = moment()  # a big chance: not a goal, so no package of its own
    injected = proposal("p-ai", package_id="pk-p-goal", package_seq=1, package_offset_ms=90_000, item_label="x",
                        status=ProposalStatus.APPROVED, decided_by="model", override_line="sneaky",
                        proposed_play_ms=1, t_in_ms=5_000, t_out_ms=9_000)
    result = SimpleNamespace(explanation=fallback_explanation(m), line="l", variants=[], failures=[],
                             proposal=injected, fan_card=None)

    async def process(_m):
        return result

    monkeypatch.setattr(main.pipeline, "process", process)
    asyncio.run(_handle_moment(m))
    p = hub.proposals["p-ai"]
    assert (p.status, p.decided_by, p.decided_at, p.override_line) == (ProposalStatus.PROPOSED, None, None, None)
    assert (p.package_id, p.package_seq, p.package_offset_ms, p.item_label) == (None, 0, 0, "")
    assert (p.t_in_ms, p.t_out_ms) == (5_000, 9_000)  # placement comes from the scheduler (code), so it stays
    assert [q.proposal_id for q in hub.proposals.values() if q.package_id == "pk-p-goal"] == ["p-goal"]

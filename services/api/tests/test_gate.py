"""The approval gate: AI text reaches a screen only inside an approved OverlayPacket."""

import asyncio

import pytest
from api.main import ViewerPrefs, _auto_hold, app, hub
from api_factories import RecordingSocket, proposal
from crq_schemas import FanCard, OverlayPacket, Persona
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient


def _viewer(persona: Persona = Persona.FAN, lang: str = "en", access: str = "none") -> RecordingSocket:
    ws = RecordingSocket()
    hub.viewers[ws] = ViewerPrefs(persona=persona, access=access, lang=lang)
    return ws


def _seed(p=None, variants=(), fan_card=None):
    p = p or proposal()
    hub.proposals[p.proposal_id] = p
    hub.results[p.moment_id] = {"variants": list(variants), "fan_card": fan_card}
    return p.proposal_id


def _variant(persona: str, lang: str, text: str, access: str = "none") -> dict:
    return {"moment_id": "mo-1", "persona": persona, "access": access, "lang": lang, "text": text, "cites": ["e-1"]}


def _aired(ws: RecordingSocket) -> list[OverlayPacket]:
    return [OverlayPacket.model_validate(m["item"]) for m in ws.of_type("overlay")]


def test_approve_stamps_packet_with_the_decision():
    viewer, pid = _viewer(), _seed()
    TestClient(app).post(f"/proposals/{pid}/approve", json={"actor": "swami"})
    (packet,) = _aired(viewer)
    entry = hub.decisions[-1]
    assert (packet.approval_id, packet.approved_by, packet.approved_at) == (entry.entry_id, "swami", hub.now())
    assert packet.source_proposal_id == pid


def test_approve_records_the_canonical_packet():
    pid = _seed()
    TestClient(app).post(f"/proposals/{pid}/approve", json={"actor": "swami"})
    (packet,) = hub.packets
    assert packet.source_proposal_id == pid and packet.approved_by == "swami"


def test_unscheduled_proposal_airs_now_for_its_proposed_duration():
    hub.clock.play_ms = 600_000
    pid = _seed(proposal(t_start_ms=1_000, t_end_ms=11_000))
    TestClient(app).post(f"/proposals/{pid}/approve")
    (packet,) = hub.packets
    assert (packet.t_in_ms, packet.t_out_ms) == (600_000, 610_000)
    assert (packet.period, packet.clock_ms) == (1, 600_000)


def test_scheduled_proposal_keeps_scheduler_times_and_displays_their_clock():
    hub.clock._period_starts[2] = 2_820_000
    pid = _seed(proposal(t_in_ms=2_900_000, t_out_ms=2_908_000))
    TestClient(app).post(f"/proposals/{pid}/approve")
    (packet,) = hub.packets
    assert (packet.t_in_ms, packet.t_out_ms, packet.period, packet.clock_ms) == (2_900_000, 2_908_000, 2, 80_000)


def test_approve_sends_each_viewer_their_persona_access_and_language_variant():
    newcomer_es, analyst, deaf_analyst = (_viewer(Persona.NEWCOMER, "es"), _viewer(Persona.ANALYST),
                                          _viewer(Persona.ANALYST, access="deaf"))
    pid = _seed(variants=[_variant("newcomer", "es", "Gran ocasión"), _variant("analyst", "en", "xG 0.41 chance"),
                          _variant("analyst", "en", "xG 0.41 chance. The score is 1 to 0.", access="deaf")])
    TestClient(app).post(f"/proposals/{pid}/approve")
    (es,), (an,), (da,) = _aired(newcomer_es), _aired(analyst), _aired(deaf_analyst)
    assert (es.line, es.profile, es.access, es.lang) == ("Gran ocasión", Persona.NEWCOMER, "none", "es")
    assert (an.line, an.profile, an.access) == ("xG 0.41 chance", Persona.ANALYST, "none")
    assert (da.line, da.profile, da.access) == ("xG 0.41 chance. The score is 1 to 0.", Persona.ANALYST, "deaf")


def test_viewer_without_a_matching_variant_gets_the_approved_base_line():
    deaf_newcomer = _viewer(Persona.NEWCOMER, access="deaf")
    pid = _seed(variants=[_variant("newcomer", "en", "Plain words, but may mention the crowd noise")])
    TestClient(app).post(f"/proposals/{pid}/approve")
    (packet,) = _aired(deaf_newcomer)
    assert packet.line == "A line" and packet.access == "none"


def test_override_line_reaches_every_viewer_verbatim():
    deaf = _viewer(access="deaf")
    pid = _seed(variants=[_variant("fan", "en", "AI text the operator replaced", access="deaf")])
    TestClient(app).post(f"/proposals/{pid}/override", json={"actor": "op", "override_line": "Operator line"})
    (packet,) = _aired(deaf)
    assert packet.line == "Operator line" and packet.verified is False


def test_fan_card_travels_inside_the_approved_packet():
    card = FanCard(card_id="fc-1", match_id="m", moment_id="mo-1", play_ms=600_000, caption="Shot saved, low left")
    deaf = _viewer(access="deaf")
    pid = _seed(fan_card=card.model_dump(mode="json"))
    TestClient(app).post(f"/proposals/{pid}/approve")
    (packet,) = _aired(deaf)
    assert packet.fan_card == card


def test_hold_and_reject_publish_nothing():
    viewer = _viewer()
    c = TestClient(app)
    held, rejected = _seed(proposal("p-h")), _seed(proposal("p-r"))
    assert c.post(f"/proposals/{held}/hold").json()["status"] == "held"
    assert c.post(f"/proposals/{rejected}/reject").json()["status"] == "rejected"
    assert viewer.sent == [] and hub.packets == []
    assert [d.action for d in hub.decisions] == ["held", "rejected"]


def test_rejected_proposal_cannot_be_approved_afterwards():
    c = TestClient(app)
    pid = _seed()
    c.post(f"/proposals/{pid}/reject")
    assert c.post(f"/proposals/{pid}/approve").status_code == 409
    assert hub.packets == []


def test_sla_timer_holds_and_never_airs():
    viewer = _viewer()
    hub.auto_hold_s = 0
    pid = _seed()
    asyncio.run(_auto_hold(pid))
    assert hub.proposals[pid].status == "held"
    assert (hub.decisions[-1].actor, hub.decisions[-1].action) == ("sla-timer", "held")
    assert viewer.sent == [] and hub.packets == []


def test_sla_timer_actor_cannot_approve_override_or_reject_over_http():
    c = TestClient(app)
    pid = _seed()
    for action, body in (("approve", {}), ("override", {"override_line": "x"}), ("reject", {})):
        assert c.post(f"/proposals/{pid}/{action}", json={"actor": "sla-timer", **body}).status_code == 403
    assert hub.decisions == [] and hub.packets == []


def test_decision_rejects_blank_actor():
    pid = _seed()
    assert TestClient(app).post(f"/proposals/{pid}/approve", json={"actor": ""}).status_code == 422


def test_viewer_socket_refuses_unsupported_language():
    # Connecting must fail outright; if the socket is accepted the block exits cleanly and raises() fails.
    with pytest.raises(WebSocketDisconnect), TestClient(app).websocket_connect("/ws/viewer?persona=fan&lang=ar"):
        pass


def test_viewer_socket_accepts_access_and_legacy_deaf_persona():
    client = TestClient(app)
    with client.websocket_connect("/ws/viewer?persona=analyst&access=deaf&lang=es"):
        assert list(hub.viewers.values()) == [ViewerPrefs(persona=Persona.ANALYST, access="deaf", lang="es")]
    # Viewer.tsx still sends the v0.2-draft value persona=deaf; it means a fan with deaf access.
    with client.websocket_connect("/ws/viewer?persona=deaf"):
        assert list(hub.viewers.values())[-1] == ViewerPrefs(persona=Persona.FAN, access="deaf")


def test_viewer_socket_refuses_unknown_persona():
    with pytest.raises(WebSocketDisconnect), TestClient(app).websocket_connect("/ws/viewer?persona=pundit"):
        pass

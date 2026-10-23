from api.main import app, hub
from api_factories import proposal
from crq_schemas import OverlayLayer, OverlayPacket, ProposalStatus
from fastapi.testclient import TestClient


def _packet(cue_id: str, t_in: int, t_out: int, layer=OverlayLayer.LOWER_THIRD, **extra) -> OverlayPacket:
    return OverlayPacket(cue_id=cue_id, match_id="m", layer=layer, t_in_ms=t_in, t_out_ms=t_out, period=1,
                         clock_ms=t_in, line=cue_id, source_proposal_id=f"p-{cue_id}", approval_id=f"d-{cue_id}",
                         approved_by="op", approved_at=hub.now(), **extra)


def _schedule(now_play_ms: int) -> dict:
    hub.clock.play_ms = now_play_ms
    return TestClient(app).get("/schedule").json()


def _cues(body: dict, layer: str, bucket: str) -> list[str]:
    return [p["cue_id"] for p in body["layers"][layer][bucket]]


def test_schedule_splits_packets_into_on_air_and_queued_by_play_time():
    hub.packets += [_packet("ended", 0, 5_000), _packet("live", 8_000, 20_000), _packet("next", 30_000, 40_000)]
    body = _schedule(10_000)
    assert _cues(body, "lower_third", "on_air") == ["live"]
    assert _cues(body, "lower_third", "queued") == ["next"]
    assert body["clock"] == {"period": 1, "clock_ms": 0, "play_ms": 10_000}


def test_schedule_lists_every_layer_even_when_empty():
    assert set(_schedule(0)["layers"]) == {layer.value for layer in OverlayLayer}


def test_replaced_cue_leaves_air_once_its_replacement_starts():
    hub.packets += [_packet("old", 0, 60_000), _packet("new", 10_000, 30_000, replaces=["old"])]
    assert _cues(_schedule(5_000), "lower_third", "on_air") == ["old"]
    assert _cues(_schedule(15_000), "lower_third", "on_air") == ["new"]


def test_same_cue_id_is_upserted_to_the_latest_packet():
    hub.packets += [_packet("c-1", 0, 10_000), _packet("c-1", 0, 20_000)]
    (live,) = _schedule(5_000)["layers"]["lower_third"]["on_air"]
    assert live["t_out_ms"] == 20_000


def test_schedule_lists_proposals_awaiting_a_decision_by_priority():
    for p in (proposal("p-low", priority=7), proposal("p-top", priority=1), proposal("p-held", priority=2)):
        hub.proposals[p.proposal_id] = p
    hub.proposals["p-held"].status = ProposalStatus.HELD
    assert [p["proposal_id"] for p in _schedule(0)["awaiting_decision"]] == ["p-top", "p-low"]

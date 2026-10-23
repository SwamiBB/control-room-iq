"""One decision fires a whole package; the gate and the audit trail still work per item."""

from api.main import ViewerPrefs, app, hub
from api_factories import RecordingSocket, proposal
from crq_schemas import OverlayLayer, OverlayPacket, ProposalStatus
from fastapi.testclient import TestClient

PK = "pk-p-g"


def _seed_package() -> list[str]:
    items = [proposal("p-g", layer=OverlayLayer.FULL_SCREEN, line="GOAL. AI line.", package_id=PK, package_seq=0),
             proposal("p-g-1", line="Finn Oakes · 1 goal", package_id=PK, package_seq=1, package_offset_ms=25_000,
                      payload={"source": "code"}),
             proposal("p-g-2", layer=OverlayLayer.TICKER, line="GOAL 42' · 1–0", package_id=PK, package_seq=2,
                      payload={"source": "code"})]
    for p in items:
        hub.proposals[p.proposal_id] = p
    hub.results["mo-1"] = {"variants": [], "fan_card": None}
    return [p.proposal_id for p in items]


def test_one_click_fires_every_item_in_running_order():
    _seed_package()
    r = TestClient(app).post(f"/packages/{PK}/approve", json={"actor": "graphics-op"})
    assert r.status_code == 200
    assert [p.source_proposal_id for p in hub.packets] == ["p-g", "p-g-1", "p-g-2"]
    assert all(p.approved_by == "graphics-op" for p in hub.packets)


def test_each_item_gets_its_own_approval_and_log_row():
    _seed_package()
    TestClient(app).post(f"/packages/{PK}/approve")
    assert len({p.approval_id for p in hub.packets}) == 3
    assert [e.package_id for e in hub.decisions] == [PK] * 3


def test_follow_ups_air_after_their_offset():
    hub.clock.play_ms = 2_480_000
    _seed_package()
    TestClient(app).post(f"/packages/{PK}/approve")
    lead, stats, ticker = hub.packets
    assert (lead.t_in_ms, stats.t_in_ms, ticker.t_in_ms) == (2_480_000, 2_505_000, 2_480_000)


def test_code_built_items_go_out_in_english_to_every_viewer():
    viewer = RecordingSocket()
    hub.viewers[viewer] = ViewerPrefs(lang="hi")
    _seed_package()
    TestClient(app).post(f"/packages/{PK}/approve")
    stats = OverlayPacket.model_validate(viewer.of_type("overlay")[1]["item"])
    assert stats.line == "Finn Oakes · 1 goal" and stats.lang == "en"


def test_an_item_dropped_on_its_own_is_skipped_by_the_package_click():
    _seed_package()
    client = TestClient(app)
    client.post("/proposals/p-g-2/reject")
    r = client.post(f"/packages/{PK}/approve")
    assert [p["proposal_id"] for p in r.json()] == ["p-g", "p-g-1"]
    assert hub.proposals["p-g-2"].status == ProposalStatus.REJECTED


def test_sla_timer_cannot_fire_a_package():
    _seed_package()
    r = TestClient(app).post(f"/packages/{PK}/approve", json={"actor": "sla-timer"})
    assert r.status_code == 403 and hub.packets == []


def test_unknown_package_and_action_are_refused():
    _seed_package()
    client = TestClient(app)
    assert client.post("/packages/pk-nope/approve").status_code == 404
    assert client.post(f"/packages/{PK}/air").status_code == 404


def test_a_decided_package_cannot_be_fired_twice():
    _seed_package()
    client = TestClient(app)
    client.post(f"/packages/{PK}/approve")
    assert client.post(f"/packages/{PK}/approve").status_code == 409


def test_metrics_endpoint_reports_the_package_click():
    _seed_package()
    for p in hub.proposals.values():
        p.proposed_at = hub.now()
    client = TestClient(app)
    client.post(f"/packages/{PK}/approve")
    m = client.get("/metrics").json()
    assert m["workload"]["operator_decisions"] == 1 and m["workload"]["packages_fired"] == 1
    assert m["turnaround"]["fired"] == 3

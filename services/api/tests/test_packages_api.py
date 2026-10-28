"""One decision fires a whole package; the gate and the audit trail still work per item."""

from api.main import ViewerPrefs, app, hub
from api_factories import RecordingSocket, match_state, moment, proposal
from crq_schemas import MomentKind, OverlayLayer, OverlayPacket, Persona, PlayerStats, ProposalStatus, TeamStats
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


def test_code_built_items_go_out_in_each_viewers_language():
    hi, en = RecordingSocket(), RecordingSocket()
    hub.viewers[hi], hub.viewers[en] = ViewerPrefs(lang="hi"), ViewerPrefs(lang="en")
    state = match_state(home=TeamStats(team="har", goals=1), away=TeamStats(team="nor"),
                        players={"har-09": PlayerStats(player_id="har-09", team="har", goals=1, shots=3, xg=0.61)})
    hub.moments["mo-1"] = moment(kind=MomentKind.GOAL, player="har-09", t_ms=2_474_000, state=state)
    _seed_package()
    TestClient(app).post(f"/packages/{PK}/approve")
    _, stats, ticker = (OverlayPacket.model_validate(m["item"]) for m in hi.of_type("overlay"))
    assert (stats.line, stats.lang, stats.verified) == ("har-09 आज · 1 गोल · 3 शॉट · xG 0.61", "hi", True)
    assert ticker.line.startswith("गोल 42' · ") and ticker.lang == "hi"
    # English viewers keep the approved line as it was built.
    assert OverlayPacket.model_validate(en.of_type("overlay")[1]["item"]).line == "Finn Oakes · 1 goal"


def test_an_analyst_gets_the_longer_scorer_stats_in_english_too():
    analyst, fan = RecordingSocket(), RecordingSocket()
    hub.viewers[analyst], hub.viewers[fan] = ViewerPrefs(persona=Persona.ANALYST), ViewerPrefs(persona=Persona.FAN)
    ps = PlayerStats(player_id="har-09", team="har", goals=1, shots=3, xg=0.61, passes=18, passes_completed=15)
    hub.moments["mo-1"] = moment(kind=MomentKind.GOAL, player="har-09", t_ms=2_474_000,
                                 state=match_state(home=TeamStats(team="har", goals=1), away=TeamStats(team="nor"),
                                                   players={"har-09": ps}))
    _seed_package()
    TestClient(app).post(f"/packages/{PK}/approve")
    to_analyst = OverlayPacket.model_validate(analyst.of_type("overlay")[1]["item"])
    assert to_analyst.line == "har-09 today · 1 goal · 3 shots · xG 0.61 · 15/18 passes" and to_analyst.lang == "en"
    assert OverlayPacket.model_validate(fan.of_type("overlay")[1]["item"]).line == "Finn Oakes · 1 goal"


def test_code_built_items_stay_in_english_without_their_moment():
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


def test_override_line_is_refused_outside_the_override_route():
    ids = _seed_package()
    client = TestClient(app)
    assert client.post(f"/packages/{PK}/approve", json={"override_line": "Same text on all three"}).status_code == 422
    for action in ("approve", "hold", "reject"):
        assert client.post(f"/proposals/{ids[0]}/{action}", json={"override_line": "x"}).status_code == 422
    assert hub.packets == [] and all(hub.proposals[i].override_line is None for i in ids)


def test_package_decision_expires_stale_items_before_choosing_what_to_fire():
    ids = _seed_package()
    for pid in ids[1:]:  # follow-ups were held long ago; the lead is still awaiting a decision
        hub.proposals[pid].status, hub.proposals[pid].proposed_play_ms = ProposalStatus.HELD, 0
    hub.clock.play_ms = 10 * 60_000
    r = TestClient(app).post(f"/packages/{PK}/approve")
    assert r.status_code == 200 and [p["proposal_id"] for p in r.json()] == ["p-g"]
    assert [p.source_proposal_id for p in hub.packets] == ["p-g"]
    assert {hub.proposals[i].status for i in ids[1:]} == {ProposalStatus.EXPIRED}

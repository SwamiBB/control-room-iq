"""The preview route is read-only: nothing it does can reach air or the decision log."""

from api.main import ViewerPrefs, app, hub
from api_factories import RecordingSocket, proposal
from crq_schemas import Persona, ProposalStatus
from fastapi.testclient import TestClient


def _seed(variants=()):
    p = proposal(line="Harbor City pressing hard.")
    hub.proposals[p.proposal_id] = p
    hub.results[p.moment_id] = {"variants": list(variants), "fan_card": None}
    return p.proposal_id


def _variant(lang: str, text: str) -> dict:
    return {"moment_id": "mo-1", "persona": "fan", "access": "none", "lang": lang, "text": text, "cites": ["e-1"]}


def test_preview_shows_the_picked_groups_in_the_order_picked():
    pid = _seed([_variant("es", "Harbor City presiona fuerte.")])
    r = TestClient(app).get(f"/proposals/{pid}/preview", params=[("view", "fan.none.es"), ("view", "fan.none.en")])
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["view"]["key"] for i in items] == ["fan.none.es.neutral", "fan.none.en.neutral"]
    assert items[0]["text"] == "Harbor City presiona fuerte." and items[0]["source"] == "variant"


def test_with_nothing_picked_it_previews_the_groups_watching_now():
    hub.viewers[RecordingSocket()] = ViewerPrefs(persona=Persona.NEWCOMER, lang="hi")
    hub.viewers[RecordingSocket()] = ViewerPrefs(persona=Persona.NEWCOMER, lang="hi")
    pid = _seed()
    items = TestClient(app).get(f"/proposals/{pid}/preview").json()["items"]
    assert [i["view"]["key"] for i in items] == ["newcomer.none.hi.neutral"]


def test_with_nobody_watching_it_previews_the_default_viewer():
    pid = _seed()
    items = TestClient(app).get(f"/proposals/{pid}/preview").json()["items"]
    assert [i["view"]["key"] for i in items] == ["fan.none.en.neutral"]


def test_preview_never_airs_logs_or_changes_the_proposal():
    viewer = RecordingSocket()
    hub.viewers[viewer] = ViewerPrefs()
    pid = _seed()
    TestClient(app).get(f"/proposals/{pid}/preview", params={"override_line": "My words"})
    assert hub.packets == [] and hub.decisions == [] and hub.deliveries == [] and viewer.sent == []
    p = hub.proposals[pid]
    assert p.status == ProposalStatus.PROPOSED and p.override_line is None


def test_bad_requests_are_refused():
    pid = _seed()
    client = TestClient(app)
    assert client.get("/proposals/p-nope/preview").status_code == 404
    assert client.get(f"/proposals/{pid}/preview", params={"view": "fan.none.fr"}).status_code == 422
    too_many = [("view", "fan.none.en")] * 13
    assert client.get(f"/proposals/{pid}/preview", params=too_many).status_code == 422


def test_picker_options_are_listed():
    groups = TestClient(app).get("/viewer-groups").json()
    assert {"key": "fan.deaf.es.neutral", "persona": "fan", "access": "deaf", "lang": "es",
            "allegiance": "neutral"} in groups

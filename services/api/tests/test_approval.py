import os

os.environ["CRQ_OFFLINE"] = "1"

from api.main import app, hub  # noqa: E402
from crq_schemas import OverlayLayer, OverlayProposal  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _seed_proposal(pid="p-test"):
    hub.proposals[pid] = OverlayProposal(proposal_id=pid, match_id="m", moment_id="mo", layer=OverlayLayer.LOWER_THIRD,
                                        t_start_ms=1000, t_end_ms=9000, line="A line", reasoning="r", priority=3)
    return pid


def test_approve_then_cannot_hold():
    c = TestClient(app)
    pid = _seed_proposal()
    r = c.post(f"/proposals/{pid}/approve", json={"actor": "swami"})
    assert r.status_code == 200 and r.json()["status"] == "aired"
    assert c.post(f"/proposals/{pid}/hold").status_code == 409
    assert c.get("/decisions").json()[-1]["actor"] == "swami"


def test_override_requires_line():
    c = TestClient(app)
    pid = _seed_proposal("p-2")
    assert c.post(f"/proposals/{pid}/override", json={"actor": "op"}).status_code == 422
    r = c.post(f"/proposals/{pid}/override", json={"actor": "op", "override_line": "Better line"})
    assert r.json()["override_line"] == "Better line"

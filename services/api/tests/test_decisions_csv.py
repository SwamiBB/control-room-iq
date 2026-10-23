import csv
import io

from api.main import app, hub
from crq_schemas import DecisionLogEntry, ProposalStatus
from fastapi.testclient import TestClient


def _log(reasoning: str | None, actor: str = "op") -> None:
    entry = DecisionLogEntry(entry_id=f"d-{len(hub.decisions)}", match_id="m", proposal_id="p",
                             action=ProposalStatus.APPROVED, actor=actor, at=hub.now(), reasoning=reasoning)
    hub.decisions.append(entry)


def _rows() -> list[list[str]]:
    r = TestClient(app).get("/decisions.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    return list(csv.reader(io.StringIO(r.text)))


def test_decisions_csv_round_trips_commas_quotes_and_newlines():
    _log('Held: "too early", crowd\nstill up')
    header, row = _rows()
    assert header == ["entry_id", "match_id", "proposal_id", "action", "actor", "at", "reasoning"]
    assert row == ["d-0", "m", "p", "approved", "op", hub.now().isoformat(), 'Held: "too early", crowd\nstill up']


def test_decisions_csv_neutralises_spreadsheet_formulas():
    _log("=HYPERLINK(\"http://x\")", actor="+op")
    _, row = _rows()
    assert row[4] == "'+op" and row[6].startswith("'=")


def test_decisions_csv_is_offered_as_a_download():
    r = TestClient(app).get("/decisions.csv")
    assert r.headers["content-disposition"] == 'attachment; filename="decisions.csv"'

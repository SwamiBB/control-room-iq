"""Downloadable exports of the decision log."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable

from crq_schemas import DecisionLogEntry

CSV_HEADER = ["entry_id", "match_id", "proposal_id", "action", "actor", "at", "reasoning"]
# Spreadsheets execute cells starting with these as formulas; actor and reasoning are free text.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: str) -> str:
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


def _row(e: DecisionLogEntry) -> list[str]:
    action = e.action.value if hasattr(e.action, "value") else str(e.action)
    return [e.entry_id, e.match_id, e.proposal_id, action, _cell(e.actor), e.at.isoformat(), _cell(e.reasoning or "")]


def decisions_to_csv(entries: Iterable[DecisionLogEntry]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    writer.writerows(_row(e) for e in entries)
    return buf.getvalue()

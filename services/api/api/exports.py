"""Downloadable exports of the decision log."""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Iterable

from crq_schemas import DecisionLogEntry

logger = logging.getLogger(__name__)

CSV_HEADER = ["entry_id", "match_id", "proposal_id", "action", "actor", "at", "reasoning", "package_id"]
# Spreadsheets execute cells starting with these as formulas; actor and reasoning are free text.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: str) -> str:
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


def _row(e: DecisionLogEntry) -> list[str]:
    action = e.action.value if hasattr(e.action, "value") else str(e.action)
    return [e.entry_id, e.match_id, e.proposal_id, action, _cell(e.actor), e.at.isoformat(), _cell(e.reasoning or ""),
            e.package_id or ""]


def decisions_to_csv(entries: Iterable[DecisionLogEntry]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    writer.writerows(_row(e) for e in entries)
    return buf.getvalue()


def history_to_csv(docs: Iterable[dict]) -> str:
    """The persisted log (decision_store.py): the same columns, plus the run each decision belongs to."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([*CSV_HEADER, "run_id", "seq"])
    for d in docs:
        try:
            entry = DecisionLogEntry.model_validate(d)
        except ValueError:  # one unreadable document must not hide the rest of the trail
            logger.warning("decision document %s skipped: it no longer matches DecisionLogEntry", d.get("id"))
            continue
        writer.writerow([*_row(entry), d.get("run_id", ""), str(d.get("seq", ""))])
    return buf.getvalue()

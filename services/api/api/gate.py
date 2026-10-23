"""ApprovalGate: the proposal state machine, the only way anything airs.

  proposed  --approve-->  approved     (operator)        --> aired
            --override--> overridden   (operator)        --> aired
            --hold------> held         (operator)
            --sla_hold--> sla_held     (sla, after 20 s with no operator action)
            --supersede-> superseded   (supersession: a higher-priority moment on the same phase or stoppage)
  held, sla_held -> approve / override / supersede (sla_held may also be held by the operator)

Only an operator can approve or override, so there is no auto-approve path and no setting that adds one.
Every transition is one Decision row; the log is exported as CSV for the audit trail.
"""

from __future__ import annotations

import csv
import io

from crq_schemas import Decision, ProposalStatus

S = ProposalStatus
RESULT = {"approve": S.APPROVED, "override": S.OVERRIDDEN, "hold": S.HELD, "sla_hold": S.SLA_HELD,
          "supersede": S.SUPERSEDED}
ALLOWED = {
    S.PROPOSED: {"approve", "override", "hold", "sla_hold", "supersede"},
    S.HELD: {"approve", "override", "supersede"},
    S.SLA_HELD: {"approve", "override", "hold", "supersede"},
}
ACTOR = {"approve": "operator", "override": "operator", "hold": "operator", "sla_hold": "sla",
         "supersede": "supersession"}
AIRS = {S.APPROVED, S.OVERRIDDEN}
CSV_FIELDS = ["decision_id", "at", "match_period", "match_minute", "match_second", "proposal_id", "action", "actor",
              "operator", "edited_line", "routed_model"]


class IllegalTransition(ValueError):
    pass


def next_status(status: ProposalStatus, action: str, actor: str) -> ProposalStatus:
    if action not in RESULT:
        raise IllegalTransition(f"unknown action {action!r}")
    if ACTOR[action] != actor:
        raise IllegalTransition(f"{action} is reserved for {ACTOR[action]}, not {actor}")
    if action not in ALLOWED.get(status, set()):
        raise IllegalTransition(f"cannot {action} a proposal that is {status.value}")
    return RESULT[action]


def to_csv(decisions: list[Decision]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_FIELDS)
    for d in decisions:
        w.writerow([d.decision_id, d.at.isoformat(), d.match_clock.period, d.match_clock.minute, d.match_clock.second,
                    d.proposal_id, d.action, d.actor, d.operator or "", d.edited_line or "", d.routed_model or ""])
    return buf.getvalue()

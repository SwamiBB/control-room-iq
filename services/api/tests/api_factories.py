"""Synthetic records for API tests. Invented teams and values only; no real match data."""

from __future__ import annotations

from crq_schemas import MatchState, Moment, MomentKind, OverlayLayer, OverlayProposal, TeamStats


def match_state(**overrides) -> MatchState:
    fields = {"match_id": "m", "seq": 1, "period": 1, "t_ms": 0, "home": TeamStats(team="har"),
              "away": TeamStats(team="nor")}
    return MatchState(**(fields | overrides))


def moment(moment_id: str = "mo-1", **overrides) -> Moment:
    fields = {"moment_id": moment_id, "match_id": "m", "t_ms": 600_000, "period": 1, "kind": MomentKind.BIG_CHANCE,
              "importance": 0.7, "team": "har", "player": "har-09", "event_ids": ["e-1"],
              "summary": "Big chance", "state": match_state()}
    return Moment(**(fields | overrides))


def proposal(proposal_id: str = "p-1", **overrides) -> OverlayProposal:
    fields = {"proposal_id": proposal_id, "match_id": "m", "moment_id": "mo-1", "layer": OverlayLayer.LOWER_THIRD,
              "t_start_ms": 1_000, "t_end_ms": 9_000, "line": "A line", "reasoning": "r", "priority": 3}
    return OverlayProposal(**(fields | overrides))

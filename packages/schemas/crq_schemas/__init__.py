"""Shared data contracts for Control Room IQ.

All services exchange these Pydantic models (as JSON) so the simulator, ingest, agents, API, and web
front end agree on one vocabulary. Pitch coordinates are 0-100 on both axes, attacking left to right
for the team in possession.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "0.1.0"


class EventType(str, Enum):
    KICKOFF = "kickoff"
    PASS = "pass"
    CARRY = "carry"
    SHOT = "shot"
    TACKLE = "tackle"
    INTERCEPTION = "interception"
    FOUL = "foul"
    CLEARANCE = "clearance"
    POSSESSION_CHANGE = "possession_change"
    PRESSURE = "pressure"
    SUBSTITUTION = "substitution"
    CARD = "card"
    HALF_END = "half_end"
    MATCH_END = "match_end"


class Player(BaseModel):
    player_id: str
    name: str
    number: int
    position: Literal["GK", "DF", "MF", "FW"]
    pace: float = Field(ge=0, le=1, description="Top speed relative to the league (0-1)")
    passing: float = Field(ge=0, le=1)
    shooting: float = Field(ge=0, le=1)
    defending: float = Field(ge=0, le=1)


class Team(BaseModel):
    team_id: str
    name: str
    short_name: str
    primary_color: str = "#1f3a93"
    formation: str = "4-3-3"
    style: Literal["possession", "direct", "press", "counter"] = "possession"
    players: list[Player]


class MatchMeta(BaseModel):
    match_id: str
    competition: str = "Synthetic League"
    venue: str
    kickoff_utc: datetime
    home: Team
    away: Team
    seed: int
    schema_version: str = SCHEMA_VERSION


class MatchEvent(BaseModel):
    event_id: str
    match_id: str
    seq: int
    t_ms: int = Field(description="Match clock in milliseconds from kickoff of the period")
    period: Literal[1, 2]
    type: EventType
    team: str | None = None
    player: str | None = None
    x: float | None = None
    y: float | None = None
    end_x: float | None = None
    end_y: float | None = None
    outcome: Literal["success", "fail", "goal", "saved", "blocked", "off_target", "n/a"] = "n/a"
    attrs: dict[str, Any] = Field(default_factory=dict)


class PlayerStats(BaseModel):
    player_id: str
    team: str
    passes: int = 0
    passes_completed: int = 0
    shots: int = 0
    goals: int = 0
    xg: float = 0.0
    tackles: int = 0
    distance_m: float = 0.0
    top_speed_kmh: float = 0.0
    pressures: int = 0


class TeamStats(BaseModel):
    team: str
    goals: int = 0
    shots: int = 0
    shots_on_target: int = 0
    xg: float = 0.0
    passes: int = 0
    passes_completed: int = 0
    possession_pct: float = 50.0
    pressures: int = 0
    ppda: float | None = Field(default=None, description="Passes allowed per defensive action")


class MatchState(BaseModel):
    match_id: str
    seq: int
    period: Literal[1, 2]
    t_ms: int
    home: TeamStats
    away: TeamStats
    players: dict[str, PlayerStats] = Field(default_factory=dict)
    momentum: list[float] = Field(
        default_factory=list, description="Rolling momentum per minute, -1 (away) to +1 (home)"
    )
    pressure_windows: list[dict[str, float]] = Field(default_factory=list)
    last_event_id: str | None = None


class MomentKind(str, Enum):
    GOAL = "goal"
    BIG_CHANCE = "big_chance"
    MOMENTUM_SHIFT = "momentum_shift"
    PRESSURE_SPIKE = "pressure_spike"
    MILESTONE = "milestone"
    SPEED_THRESHOLD = "speed_threshold"
    CARD = "card"
    HALF_END = "half_end"
    MATCH_END = "match_end"


class Moment(BaseModel):
    moment_id: str
    match_id: str
    t_ms: int
    period: Literal[1, 2]
    kind: MomentKind
    importance: float = Field(ge=0, le=1)
    team: str | None = None
    player: str | None = None
    event_ids: list[str]
    summary: str = Field(description="Deterministic, template-generated one-liner (ground truth)")
    state: MatchState


class Explanation(BaseModel):
    moment_id: str
    headline: str
    why_it_matters: str
    pattern: Literal["control", "chaos", "pressure_shift", "rhythm_change", "individual", "set_piece"]
    cites: list[str] = Field(description="Event IDs the explanation relies on")
    confidence: float = Field(ge=0, le=1)


class Persona(str, Enum):
    ANALYST = "analyst"
    FAN = "fan"
    ACCESSIBILITY = "accessibility"


Lang = Literal["en", "es", "hi", "ar"]


class NarrativeVariant(BaseModel):
    moment_id: str
    persona: Persona
    lang: Lang
    text: str
    audio_url: str | None = None
    cites: list[str] = Field(default_factory=list)
    faithfulness: float | None = Field(default=None, description="Foundry evaluation score 0-1")


class OverlayLayer(str, Enum):
    LOWER_THIRD = "lower_third"
    STAT_PANEL = "stat_panel"
    HEATMAP = "heatmap"
    TICKER = "ticker"
    FULL_SCREEN = "full_screen"


class ProposalStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    HELD = "held"
    OVERRIDDEN = "overridden"
    AIRED = "aired"
    EXPIRED = "expired"


class OverlayProposal(BaseModel):
    proposal_id: str
    match_id: str
    moment_id: str
    layer: OverlayLayer
    t_start_ms: int
    t_end_ms: int
    line: str = Field(description="On-air text as proposed by the producer agent")
    payload: dict[str, Any] = Field(default_factory=dict, description="Graphic data for the renderer")
    reasoning: str
    priority: float = Field(ge=0, le=1)
    faithfulness: float | None = None
    status: ProposalStatus = ProposalStatus.PROPOSED
    decided_by: str | None = None
    decided_at: datetime | None = None
    override_line: str | None = None


class OverlayItem(BaseModel):
    """What the renderer receives: timed, machine-readable, approved."""

    item_id: str
    match_id: str
    layer: OverlayLayer
    t_start_ms: int
    t_end_ms: int
    line: str
    payload: dict[str, Any]
    lang: Lang = "en"
    persona: Persona = Persona.FAN
    source_proposal_id: str


class DecisionLogEntry(BaseModel):
    entry_id: str
    match_id: str
    proposal_id: str
    action: ProposalStatus
    actor: str
    at: datetime
    reasoning: str | None = None

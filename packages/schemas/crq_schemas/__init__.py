"""Shared data contracts for Control Room IQ (v0.2, October 23, 2026).

All services exchange these Pydantic models (as JSON) so the simulator, ingest, agents, API, and web
front end agree on one vocabulary. Pitch coordinates are 0-100 on both axes, attacking left to right
for the team in possession.

Design rules encoded here (see docs/CHANGES-2026-10-23.md):
- Time: `play_ms` is monotonic play time from the first kickoff and is what everything is SCHEDULED on;
  `period` + `t_ms` (clock within the period) is what is DISPLAYED.
- Gate: generated text reaches a screen only inside an `OverlayPacket`, which requires approval fields.
- Cues are code, captions are AI: `FanCue` carries no generated text and may air immediately;
  `FanCard` is generated text and travels only after approval.
- Model choice is visible: every agent output records `routing` and `model_served`.
- Personalization has two independent axes: `Persona` (how much the viewer knows) and `Access` (how
  they take in the match). A deaf analyst is `persona=analyst, access=deaf`.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "0.2.0"

Lang = Literal["en", "es", "hi"]
Routing = Literal["quality", "balanced", "cost", "fallback", "template"]


# ---------------------------------------------------------------------------------------------
# Teams and match metadata
# ---------------------------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------------------------
# Raw events
# ---------------------------------------------------------------------------------------------


class EventType(str, Enum):
    KICKOFF = "kickoff"
    PASS = "pass"
    CARRY = "carry"
    SHOT_TAKEN = "shot_taken"  # the strike, before the outcome is known (crowd rises); same phase_id as the shot
    SHOT = "shot"  # the outcome
    TACKLE = "tackle"
    INTERCEPTION = "interception"
    FOUL = "foul"
    CLEARANCE = "clearance"
    POSSESSION_CHANGE = "possession_change"
    PRESSURE = "pressure"
    STOPPAGE = "stoppage"  # play stops: reason, against whom, restart
    WHISTLE = "whistle"  # the audible event itself, one per blow
    CROWD = "crowd"  # synthetic crowd level, so a deaf viewer can be told what the crowd is reacting to
    SUBSTITUTION = "substitution"
    CARD = "card"
    HALF_END = "half_end"
    MATCH_END = "match_end"


StoppageReason = Literal[
    "foul", "offside", "ball_out", "injury", "goal", "half_end", "match_end", "var_review", "substitution", "other"
]
Restart = Literal["free_kick", "penalty", "corner", "goal_kick", "throw_in", "kickoff", "drop_ball", "none"]


class MatchEvent(BaseModel):
    """One raw event.

    `attrs` keys by type (all optional):
      pass:        receiver, distance_m, difficulty, progressive, ball_speed_kmh, key_pass (bool)
      carry:       distance_m, speed_kmh
      shot_taken:  xg, body, zone
      shot:        xg, speed_kmh, body, keeper, blocker, assist_by, assist_event_id, zone
      pressure:    intensity, target
      stoppage:    reason (StoppageReason), against_team, against_player, restart (Restart), restart_x, restart_y
      whistle:     kind, stoppage_id
      crowd:       crowd_level (0-1), trigger_event_id
      foul/card:   card (yellow|red|second_yellow), reason, stoppage_id
      substitution: off, on, off_position, on_position
    """

    event_id: str
    match_id: str
    seq: int
    play_ms: int = Field(default=0, description="Monotonic play time from first kickoff; schedule on this")
    t_ms: int = Field(description="Match clock within the period, for display")
    period: Literal[1, 2]
    type: EventType
    team: str | None = None
    player: str | None = None
    x: float | None = None
    y: float | None = None
    end_x: float | None = None
    end_y: float | None = None
    outcome: Literal["success", "fail", "goal", "saved", "blocked", "off_target", "post", "n/a"] = "n/a"
    phase_id: str | None = Field(default=None, description="Groups the actions of one possession")
    stoppage_id: str | None = Field(default=None, description="Links whistle, foul, card and restart")
    attrs: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------------------------
# Derived state
# ---------------------------------------------------------------------------------------------


class PlayerStats(BaseModel):
    player_id: str
    team: str
    passes: int = 0
    passes_completed: int = 0
    key_passes: int = 0
    assists: int = 0
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
    xg_last_5min: float = 0.0
    shots_last_5min: int = 0


class ShotRecord(BaseModel):
    event_id: str
    play_ms: int
    period: Literal[1, 2]
    t_ms: int
    team: str
    player: str
    xg: float
    outcome: str
    zone: str = Field(default="", description="Plain-language position, e.g. 'edge of the box, left'")
    chance_rank: int = Field(default=0, description="1 = best chance of the match so far")


class StoppageInfo(BaseModel):
    stoppage_id: str
    play_ms: int
    reason: StoppageReason
    against_team: str | None = None
    against_player: str | None = None
    restart: Restart = "none"
    restart_x: float | None = None
    restart_y: float | None = None


class PhaseSummary(BaseModel):
    phase_id: str
    team: str
    start_play_ms: int
    passes: int = 0
    progressive_passes: int = 0
    players: list[str] = Field(default_factory=list)
    ended_with: str | None = Field(default=None, description="shot | turnover | foul | stoppage")


class RecapPoint(BaseModel):
    play_ms: int
    period: Literal[1, 2]
    t_ms: int
    kind: str
    importance: float
    summary: str
    event_ids: list[str]


class MatchState(BaseModel):
    match_id: str
    seq: int
    period: Literal[1, 2]
    t_ms: int
    play_ms: int = 0
    home: TeamStats
    away: TeamStats
    players: dict[str, PlayerStats] = Field(default_factory=dict)
    momentum: list[float] = Field(default_factory=list, description="Rolling momentum per minute, -1 (away) to +1 (home)")
    momentum_label: Literal["home_pushing", "balanced", "away_pushing"] = "balanced"
    pressure_windows: list[dict[str, float]] = Field(default_factory=list)
    pressure_trend: Literal["rising", "steady", "falling"] = "steady"
    shots: list[ShotRecord] = Field(default_factory=list)
    last_stoppage: StoppageInfo | None = None
    current_phase: PhaseSummary | None = None
    recap_points: list[RecapPoint] = Field(default_factory=list)
    last_event_id: str | None = None


# ---------------------------------------------------------------------------------------------
# Moments
# ---------------------------------------------------------------------------------------------


class MomentKind(str, Enum):
    GOAL = "goal"
    BIG_CHANCE = "big_chance"
    MOMENTUM_SHIFT = "momentum_shift"
    PRESSURE_SPIKE = "pressure_spike"
    MILESTONE = "milestone"
    SPEED_THRESHOLD = "speed_threshold"
    STOPPAGE = "stoppage"
    CARD = "card"
    SUBSTITUTION = "substitution"
    HALF_END = "half_end"
    MATCH_END = "match_end"


class Moment(BaseModel):
    moment_id: str
    match_id: str
    play_ms: int = 0
    t_ms: int
    period: Literal[1, 2]
    kind: MomentKind
    beat: Literal["chance", "result", "none"] = Field(
        default="none", description="A big chance is two moments: 'chance' on shot_taken, 'result' on shot"
    )
    importance: float = Field(ge=0, le=1)
    team: str | None = None
    player: str | None = None
    event_ids: list[str]
    summary: str = Field(description="Deterministic, template-generated one-liner (ground truth)")
    state: MatchState


# ---------------------------------------------------------------------------------------------
# Agent outputs
# ---------------------------------------------------------------------------------------------


class AgentMeta(BaseModel):
    routing: Routing = "template"
    model_served: str | None = Field(default=None, description="From response.model of the router deployment")
    latency_ms: int | None = None


class Explanation(BaseModel):
    moment_id: str
    headline: str
    why_it_matters: str
    pattern: Literal["control", "chaos", "pressure_shift", "rhythm_change", "individual", "set_piece"]
    cites: list[str] = Field(description="Event IDs the explanation relies on")
    confidence: float = Field(ge=0, le=1)
    meta: AgentMeta = Field(default_factory=AgentMeta)


class Persona(str, Enum):
    """How much the viewer knows: sets wording and depth."""

    NEWCOMER = "newcomer"  # explains terms in plain language, e.g. chance quality instead of xG
    FAN = "fan"
    ANALYST = "analyst"


# How the viewer takes in the match: delivery rules applied on top of any persona. "deaf": no sound
# references; where on the pitch, who, and the score after. Deaf viewers also receive FanCue/FanCard.
Access = Literal["none", "deaf"]


class NarrativeVariant(BaseModel):
    moment_id: str
    persona: Persona
    access: Access = "none"
    lang: Lang
    text: str
    cites: list[str] = Field(default_factory=list)
    faithfulness: float | None = Field(default=None, description="Foundry evaluation score 0-1")
    meta: AgentMeta = Field(default_factory=AgentMeta)


# ---------------------------------------------------------------------------------------------
# Deaf-fan records
# ---------------------------------------------------------------------------------------------


class FanCue(BaseModel):
    """Deterministic visual stand-in for what the crowd and the whistle would tell a hearing viewer.

    Contains no generated text, so it may air immediately (<= 1 s after the event) without passing the
    operator gate. Logged like any aired item.
    """

    cue_id: str
    match_id: str
    moment_id: str
    play_ms: int
    kind: Literal["chance", "goal", "whistle", "crowd_rising", "crowd_roar", "crowd_groan", "card"]
    team: str | None = None
    direction: Literal["left_to_right", "right_to_left"] | None = None
    crowd_level: float = Field(default=0.0, ge=0, le=1)
    pulse: Literal["tap", "pulse", "wave", "surge"] = "pulse"
    hold_ms: int = 1500


class FanContext(BaseModel):
    past: str | None = None
    now: str | None = None
    next: str | None = None


class FanDetail(BaseModel):
    shooter: str | None = None
    zone: str | None = None
    outcome: str | None = None
    chance_quality: str | None = Field(default=None, description="Plain language, e.g. 'about 1 in 3 chances like this go in'")
    xg: float | None = None
    score: str | None = None


class FanCard(BaseModel):
    """Generated caption for the deaf viewer; travels only inside an approved OverlayPacket."""

    card_id: str
    match_id: str
    moment_id: str
    beat: Literal["chance", "result", "none"] = "result"
    play_ms: int
    lang: Lang = "en"
    caption: str
    detail: FanDetail = Field(default_factory=FanDetail)
    context: FanContext = Field(default_factory=FanContext)
    cites: list[str] = Field(default_factory=list)
    faithfulness: float | None = None
    hold_ms: int = 8000
    meta: AgentMeta = Field(default_factory=AgentMeta)


# ---------------------------------------------------------------------------------------------
# Producer, scheduler, approval, packets
# ---------------------------------------------------------------------------------------------


class OverlayLayer(str, Enum):
    LOWER_THIRD = "lower_third"
    STAT_PANEL = "stat_panel"
    HEATMAP = "heatmap"
    TICKER = "ticker"
    FULL_SCREEN = "full_screen"
    CAPTION = "caption"  # deaf-fan captions; never queues, a new line always cuts the running one
    PLAYER_TAG = "player_tag"
    PITCH_OVERLAY = "pitch_overlay"


class ProposalStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    HELD = "held"
    OVERRIDDEN = "overridden"
    REJECTED = "rejected"
    AIRED = "aired"
    EXPIRED = "expired"


class EvidenceLine(BaseModel):
    event_id: str
    text: str = Field(description="Readable rendering of the cited event, e.g. \"57:12 Marsh shot, xG 0.38, saved\"")


class Alternative(BaseModel):
    layer: OverlayLayer
    line: str
    rejected_because: str


class HoldAdvice(BaseModel):
    recommend_hold: bool = False
    reason: str | None = Field(default=None, description="e.g. 'pressure rising; a goal may follow'")
    until_play_ms: int | None = None


class OverlayProposal(BaseModel):
    proposal_id: str
    cue_id: str = Field(default="", description="Stable id for the aired packet; the renderer upserts by it")
    match_id: str
    moment_id: str
    layer: OverlayLayer
    # Scheduling (assigned by the scheduler module, not by the agent)
    t_in_ms: int = Field(default=0, description="Play-time start")
    t_out_ms: int = Field(default=0, description="Play-time end")
    priority: int = Field(default=5, ge=1, description="1 = highest; goal/red card preempt the lower third")
    replaces: list[str] = Field(default_factory=list, description="cue_ids this packet supersedes")
    min_hold_ms: int = 4000
    max_delay_ms: int = 20000
    # Display timing (derived from t_in/t_out for the operator)
    t_start_ms: int = 0
    t_end_ms: int = 0
    # Content (from the producer agent)
    line: str = Field(description="On-air text as proposed")
    payload: dict[str, Any] = Field(default_factory=dict, description="Graphic data for the renderer")
    reasoning: str
    alternatives: list[Alternative] = Field(default_factory=list)
    evidence: list[EvidenceLine] = Field(default_factory=list)
    hold_advice: HoldAdvice = Field(default_factory=HoldAdvice)
    faithfulness: float | None = None
    fallback: bool = Field(default=False, description="True when the template fallback produced this")
    # Decision
    status: ProposalStatus = ProposalStatus.PROPOSED
    decided_by: str | None = None
    decided_at: datetime | None = None
    override_line: str | None = None
    meta: AgentMeta = Field(default_factory=AgentMeta)


class OverlayPacket(BaseModel):
    """What a renderer receives. Approval fields are REQUIRED: the renderer refuses packets without them."""

    cue_id: str
    match_id: str
    layer: OverlayLayer
    t_in_ms: int
    t_out_ms: int
    period: Literal[1, 2]
    clock_ms: int
    priority: int = 5
    replaces: list[str] = Field(default_factory=list)
    min_hold_ms: int = 4000
    line: str
    payload: dict[str, Any] = Field(default_factory=dict)
    profile: Persona = Persona.FAN
    access: Access = "none"
    lang: Lang = "en"
    verified: bool = True
    fallback: bool = False
    evidence: list[str] = Field(default_factory=list, description="Event IDs")
    source_proposal_id: str
    approval_id: str
    approved_by: str
    approved_at: datetime
    fan_card: FanCard | None = None


# Backward-compatible alias for code written against v0.1.
OverlayItem = OverlayPacket


class DecisionAction(str, Enum):
    APPROVE = "approved"
    HOLD = "held"
    OVERRIDE = "overridden"
    REJECT = "rejected"
    EXPIRE = "expired"
    SLA_HOLD = "sla_held"


class DecisionLogEntry(BaseModel):
    entry_id: str
    match_id: str
    proposal_id: str
    action: DecisionAction | ProposalStatus
    actor: str
    at: datetime
    reasoning: str | None = None


# ---------------------------------------------------------------------------------------------
# Catch-up card
# ---------------------------------------------------------------------------------------------


class RecapRequest(BaseModel):
    match_id: str
    minutes: Literal[10, 20, 30] = 10
    persona: Persona = Persona.FAN
    access: Access = "none"
    lang: Lang = "en"


class Recap(BaseModel):
    match_id: str
    from_play_ms: int
    to_play_ms: int
    score: str
    points: list[RecapPoint]
    text: str = Field(description="Generated summary; empty until approved when used on broadcast")
    meta: AgentMeta = Field(default_factory=AgentMeta)

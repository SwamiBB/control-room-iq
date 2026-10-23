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

SCHEMA_VERSION = "0.2.0"  # 0.2: additive changes from docs/SCHEMA_CHANGES.md


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
    # 0.2 additions. kloppy names where one exists; the rest are our extensions.
    SHOT_TAKEN = "shot_taken"  # the strike, before the shot's outcome is known
    STOPPAGE = "stoppage"  # attrs: reason, against, restart
    WHISTLE = "whistle"  # attrs: kind (stop / restart / half_end / match_end)
    CROWD = "crowd"  # attrs: level 0-1, steady cadence
    BALL_OUT = "ball_out"
    RECOVERY = "recovery"


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
    secondary_color: str | None = None
    crest: str | None = Field(default=None, description="Crest asset path for the fictional club")


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
    attrs: dict[str, Any] = Field(default_factory=dict, description="Qualifiers (kloppy / Opta style)")
    minute: int | None = Field(default=None, description="Opta-style clock from match kickoff; period 2 starts at 45")
    second: int | None = None
    phase_id: str | None = Field(default=None, description="Possession phase; same id on build-up and shot")
    stoppage_id: str | None = Field(default=None, description="Links whistle, foul, card, stoppage and restart")
    frame: int | None = Field(default=None, description="Tracking frame at the time of the event")


class TrackingFrame(BaseModel):
    """One tick of the tracking-style stream; consumed by the pitch view only."""

    frame: int
    period: Literal[1, 2]
    t_ms: int
    ball: tuple[float, float]
    players: dict[str, tuple[float, float]]


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


class ShotLedgerEntry(BaseModel):
    event_id: str
    minute: int
    team: str
    player: str
    xg: float
    outcome: str
    zone: str
    chance_rank: int = Field(description="1 = best chance of the match so far, by xG")


class TeamWindow(BaseModel):
    """Trailing 5-minute window for one team."""

    xg_5m: float = 0.0
    shots_5m: int = 0


class PressureTrend(BaseModel):
    value: float = 0.0
    slope: float = Field(default=0.0, description="Signed change across the last two windows; hold-advice input")


class PhaseSummary(BaseModel):
    phase_id: str
    team: str
    passes: int = 0
    players: list[str] = Field(default_factory=list)
    started_zone: str | None = None
    started_minute: int | None = None


class StoppageSummary(BaseModel):
    stoppage_id: str
    reason: Literal["foul", "offside", "injury", "ball_out"]
    against: str | None = None
    restart: str | None = None
    card: Literal["yellow", "second_yellow", "red"] | None = None


class RecapPoint(BaseModel):
    minute: int
    kind: str
    text_template: str
    cites: list[str] = Field(default_factory=list)


class PlayerFocus(BaseModel):
    distance_km: float = 0.0
    top_speed_kmh: float = 0.0
    sprints: int = 0
    passes_completed: int = 0
    xg: float = 0.0


class Milestone(BaseModel):
    subject: str = Field(description="Player or team id")
    kind: str
    value: float
    event_id: str


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
    # 0.2 derived state (docs/SCHEMA_CHANGES.md section 3)
    minute: int | None = None
    shot_ledger: list[ShotLedgerEntry] = Field(default_factory=list)
    windows: dict[str, TeamWindow] = Field(default_factory=dict, description="Keyed by team id")
    pressure_trend: dict[str, PressureTrend] = Field(default_factory=dict, description="Keyed by team id")
    momentum_label: Literal["home_on_top", "away_on_top", "even", "swinging"] | None = None
    zone: str | None = Field(default=None, description="Zone namer output for the last event")
    phase: PhaseSummary | None = None
    last_stoppage: StoppageSummary | None = None
    recap_points: list[RecapPoint] = Field(default_factory=list)
    player_focus: dict[str, PlayerFocus] = Field(default_factory=dict)
    milestones: list[Milestone] = Field(default_factory=list)


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
    STOPPAGE = "stoppage"
    RED_CARD = "red_card"
    SHOT = "shot"  # strike beat of any shot (beat = "strike"); cue only, never a proposal


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
    beat: Literal["strike", "result", "single"] = "single"
    trigger_event_id: str | None = None
    phase_id: str | None = None
    stoppage_id: str | None = None
    priority: int = Field(default=0, ge=0, le=100, description="From the priority table; drives supersession")
    snapshot: dict[str, Any] = Field(
        default_factory=dict, description="The slice the agents see for this moment type; cites resolve inside it"
    )


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
    BADGE = "badge"


class ProposalStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    HELD = "held"
    OVERRIDDEN = "overridden"
    AIRED = "aired"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    SLA_HELD = "sla_held"


class HoldAdvice(BaseModel):
    """Computed in code from MatchState; the Producer may word it but never decides it."""

    recommend: Literal["air", "hold"]
    reason: str
    horizon_s: int = 20


class Provenance(BaseModel):
    source: Literal["model", "template"]
    agent: str
    verdict: str | None = None
    attempts: int = 1
    routed_model: str | None = None


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
    window_id: str | None = Field(default=None, description="One story per window")
    hold_advice: HoldAdvice | None = None
    evidence: list[dict[str, Any]] = Field(
        default_factory=list, description="[{event_id, field, value}] behind every number in the line"
    )
    alternatives: list[dict[str, str]] = Field(default_factory=list, description="[{layer, reason_rejected}]")
    provenance: Provenance | None = None


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


# ---------- 0.2 experience records (docs/SCHEMA_CHANGES.md section 5) ----------

CUE_DUE_MS = 1000  # strike cue, from shot_taken
CAPTION_DUE_MS = 2000  # result caption, from shot


class MatchClock(BaseModel):
    period: Literal[1, 2]
    minute: int
    second: int


class StrikeCue(BaseModel):
    """Beat one of a big chance: shot_taken + crowd level, straight to the viewer, no model in the path."""

    cue_id: str
    match_id: str
    event_id: str
    team: str
    direction: Literal["left", "center", "right"]
    crowd_level: float = Field(ge=0, le=1)
    clock: MatchClock


class ChanceDetail(BaseModel):
    chance_quality: str = Field(description='Plain language, e.g. "about 1 in 3 chances like this go in"')
    xg: float


class CardContext(BaseModel):
    past: str | None = None
    now: str | None = None
    next: str | None = None


class FanCardTiming(BaseModel):
    cue_due_ms: int = CUE_DUE_MS
    caption_due_ms: int = CAPTION_DUE_MS


class FanCard(BaseModel):
    card_id: str
    match_id: str
    moment_id: str
    persona: Persona = Persona.ACCESSIBILITY  # accessibility = the deaf fan (visual narration)
    lang: Lang = "en"
    caption: str
    detail: ChanceDetail | None = None
    context: CardContext = Field(default_factory=CardContext)
    cites: list[str] = Field(default_factory=list)
    faithfulness: float | None = None
    released_by: str | None = Field(default=None, description="decision_id; nothing reaches the fan without one")
    timing: FanCardTiming = Field(default_factory=FanCardTiming)


class RecapCard(BaseModel):
    recap_id: str
    match_id: str
    kind: Literal["half_time", "full_time"]
    persona: Persona = Persona.FAN
    lang: Lang = "en"
    score: tuple[int, int]
    points: list[RecapPoint]


class PlayerLine(BaseModel):
    player_id: str
    name: str
    number: int
    team: str
    line: str
    stats: dict[str, float] = Field(default_factory=dict)
    cites: list[str] = Field(default_factory=list)


class ScheduledItem(BaseModel):
    proposal_id: str
    layer: OverlayLayer
    t_start_ms: int
    t_end_ms: int


class ScreenState(BaseModel):
    """Written only by the layer scheduler."""

    match_id: str
    t_ms: int
    on_air: list[ScheduledItem] = Field(default_factory=list)
    queued: list[ScheduledItem] = Field(default_factory=list)
    held: list[ScheduledItem] = Field(default_factory=list)


class Decision(BaseModel):
    """One row per proposal state transition. There is no auto-approve action."""

    decision_id: str
    match_id: str
    proposal_id: str
    action: Literal["approve", "hold", "override", "sla_hold", "supersede"]
    actor: Literal["operator", "sla", "supersession"]
    operator: str | None = None
    at: datetime
    match_clock: MatchClock
    edited_line: str | None = None
    routed_model: str | None = None


class EvaluationRecord(BaseModel):
    """One row per agent call; the table the Foundry evaluation reads."""

    record_id: str
    match_id: str
    moment_id: str
    agent: str
    routed_model: str | None = None
    snapshot: dict[str, Any]
    output: str
    cites: list[str] = Field(default_factory=list)
    latency_ms: int
    decision_id: str | None = None
    edited_line: str | None = None
    source: Literal["model", "template"] | None = Field(default=None, description="template = deterministic fallback")
    persona: Persona | None = None  # personalizer rows: one per persona and language
    lang: Lang | None = None

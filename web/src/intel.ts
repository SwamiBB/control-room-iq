// Match intelligence (hackathon expectation ii): player speed and distance with threshold indicators,
// pass quality (distance, accuracy, difficulty) and ball and shot speed. The stats engine computes every
// number; this file only types and formats them. Mirrors crq_schemas v0.2 (ThresholdIndicator, PassQuality,
// MomentMetrics) and the agents' `payload.intel` block.

export type MetricKind = "top_speed" | "sprint" | "distance" | "pass_difficulty" | "pass_distance" | "ball_speed" | "shot_speed";
export type DifficultyLabel = "routine" | "testing" | "hard" | "very_hard";

export type ThresholdIndicator = {
  kind: MetricKind; player?: string | null; team?: string | null; event_id?: string | null; play_ms?: number;
  value: number; threshold: number; unit: "km/h" | "m" | "km" | "rating"; label?: string;
};
export type PassQuality = {
  event_id: string; play_ms?: number; team: string; player: string; receiver?: string | null;
  distance_m: number; difficulty: number; difficulty_label?: DifficultyLabel; accuracy_pct?: number | null;
  ball_speed_kmh?: number | null; completed?: boolean; progressive?: boolean; key_pass?: boolean;
};
export type MomentMetrics = {
  player?: string | null; player_speed_kmh?: number | null; player_top_speed_kmh?: number | null;
  player_distance_km?: number | null; player_sprints?: number | null; key_pass?: PassQuality | null;
  shot_speed_kmh?: number | null; ball_speed_kmh?: number | null; thresholds?: ThresholdIndicator[];
  short?: string | null; // set by the agents' code on payload.intel
  names?: Record<string, string>; // player id -> display name for the ids in this block (match_intel.intel_payload)
};
export type PlayerIntel = {
  player_id: string; team: string; top_speed_kmh: number; distance_m: number; sprints?: number;
  passes: number; passes_completed: number; avg_pass_distance_m?: number; avg_pass_difficulty?: number;
  hard_passes_completed?: number; max_shot_speed_kmh?: number;
};
export type IntelState = {
  home: { team: string; passes: number; passes_completed: number; pass_accuracy_pct?: number | null; max_shot_speed_kmh?: number };
  away: { team: string; passes: number; passes_completed: number; pass_accuracy_pct?: number | null; max_shot_speed_kmh?: number };
  players: Record<string, PlayerIntel>;
  shots: { event_id: string; player: string; team: string; xg: number; outcome: string; speed_kmh?: number | null }[];
  last_pass?: PassQuality | null;
  thresholds?: ThresholdIndicator[];
};
export type NameOf = (playerId?: string | null) => string;

// Viewer register for the numbers: newcomer gets words, fan one whole number, analyst the full figures (one decimal).
export type IntelRegister = "newcomer" | "fan" | "analyst";

const BANDS: [number, DifficultyLabel][] = [[0.8, "very_hard"], [0.6, "hard"], [0.35, "testing"]];
export const difficultyLabel = (d: number): DifficultyLabel => BANDS.find(([floor]) => d >= floor)?.[1] ?? "routine";
export const DIFFICULTY_TEXT: Record<DifficultyLabel, string> = { routine: "Routine", testing: "Testing", hard: "Hard", very_hard: "Very hard" };

const num = (v: number, dp = 1) => (Number.isInteger(v) ? String(v) : v.toFixed(dp));
export const kmh = (v?: number | null) => (v == null ? "–" : `${num(v)} km/h`);
export const metres = (v?: number | null) => (v == null ? "–" : `${num(v)} m`);
export const km = (v?: number | null) => (v == null ? "–" : `${v.toFixed(2)} km`);
export const pct = (v?: number | null) => (v == null ? "–" : `${num(v)}%`);

export const accuracy = (t: { passes: number; passes_completed: number; pass_accuracy_pct?: number | null }) =>
  t.pass_accuracy_pct ?? (t.passes ? Math.round((1000 * t.passes_completed) / t.passes) / 10 : null);

export const passLabel = (p: PassQuality): DifficultyLabel =>
  p.difficulty_label && p.difficulty_label !== "routine" ? p.difficulty_label : difficultyLabel(p.difficulty);

const KIND_TEXT: Record<MetricKind, string> = {
  top_speed: "Top speed", sprint: "Sprint", distance: "Distance", pass_difficulty: "Pass difficulty",
  pass_distance: "Long pass", ball_speed: "Ball speed", shot_speed: "Shot speed",
};
export const thresholdKind = (k: MetricKind) => KIND_TEXT[k] ?? k;
export const thresholdLabel = (t: ThresholdIndicator) => {
  if (t.label) return t.label;
  const unit = t.unit === "rating" ? "" : ` ${t.unit}`;
  return `${num(t.value)}${unit} (threshold ${num(t.threshold)}${unit})`;
};

export type Chip = { key: string; label: string; value: string; tone?: "alert" | "hot" | "info" };

/** Chips for one moment or graphic, in the viewer's register. Numbers are shown exactly as the stats engine sent them. */
export function intelChips(m: MomentMetrics | null | undefined, name: NameOf, register: IntelRegister = "analyst"): Chip[] {
  if (!m) return [];
  const chips: Chip[] = [];
  const quoted = new Set((m.thresholds ?? []).map((t) => t.value));
  for (const [i, t] of (m.thresholds ?? []).entries()) {
    const who = t.player ? name(t.player) : "Ball";
    chips.push(register === "newcomer"
      ? { key: `t${i}`, label: who, value: t.kind === "top_speed" || t.kind === "sprint" ? "One of the fastest runs" : thresholdKind(t.kind), tone: "alert" }
      : { key: `t${i}`, label: `${thresholdKind(t.kind)} · ${who}`, value: register === "fan" ? `${t.unit === "rating" ? t.value.toFixed(2) : Math.round(t.value)}${t.unit === "rating" ? "" : ` ${t.unit}`}` : thresholdLabel(t), tone: "alert" });
  }
  const kp = m.key_pass;
  if (kp) {
    const label = passLabel(kp);
    if (register === "newcomer") chips.push({ key: "pass", label: `Pass by ${name(kp.player)}`, value: `${DIFFICULTY_TEXT[label]} to complete`, tone: label === "routine" ? "info" : "hot" });
    else if (register === "fan") chips.push({ key: "pass", label: `Pass by ${name(kp.player)}`, value: `${Math.round(kp.distance_m)} m · ${DIFFICULTY_TEXT[label]}`, tone: "hot" });
    else {
      chips.push({ key: "pass", label: `Pass · ${name(kp.player)}${kp.receiver ? ` → ${name(kp.receiver)}` : ""}`, value: metres(kp.distance_m), tone: "info" });
      chips.push({ key: "diff", label: "Difficulty", value: `${kp.difficulty.toFixed(2)} · ${DIFFICULTY_TEXT[label]}`, tone: label === "very_hard" || label === "hard" ? "hot" : "info" });
      if (kp.accuracy_pct != null) chips.push({ key: "acc", label: "Passer accuracy", value: pct(kp.accuracy_pct), tone: "info" });
      if (kp.ball_speed_kmh != null) chips.push({ key: "bsp", label: "Ball speed", value: kmh(kp.ball_speed_kmh), tone: "info" });
    }
  }
  if (m.shot_speed_kmh != null) chips.push({ key: "shot", label: "Shot speed", value: register === "newcomer" ? (m.shot_speed_kmh >= 100 ? "A thunderous strike" : "Struck firmly") : kmh(m.shot_speed_kmh), tone: "hot" });
  if (register !== "newcomer") {
    if (m.player_speed_kmh != null && !quoted.has(m.player_speed_kmh)) chips.push({ key: "spd", label: `Speed · ${name(m.player)}`, value: kmh(m.player_speed_kmh), tone: "info" });
    if (register === "analyst" && m.player_distance_km != null)
      chips.push({ key: "dist", label: `Distance · ${name(m.player)}`, value: `${km(m.player_distance_km)}${m.player_sprints ? ` · ${m.player_sprints} sprints` : ""}`, tone: "info" });
  }
  return register === "fan" ? chips.slice(0, 2) : register === "newcomer" ? chips.slice(0, 1) : chips;
}

export type Leader = { player_id: string; team: string; value: number };

/** Top N players by a running total; zeros are left out. */
export function leaders(state: IntelState | null | undefined, by: "top_speed_kmh" | "distance_m" | "sprints", n = 5): Leader[] {
  if (!state) return [];
  return Object.values(state.players)
    .map((p) => ({ player_id: p.player_id, team: p.team, value: Number(p[by] ?? 0) }))
    .filter((l) => l.value > 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, n);
}

/** The fastest shot so far, from the shot ledger (speed is filled by the stats engine). */
export function fastestShot(state: IntelState | null | undefined) {
  return (state?.shots ?? []).filter((s) => s.speed_kmh != null).sort((a, b) => (b.speed_kmh ?? 0) - (a.speed_kmh ?? 0))[0] ?? null;
}

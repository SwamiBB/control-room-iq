import type { MomentMetrics } from "./intel";

export const API = import.meta.env.VITE_API_URL ?? "";
export const WS = API ? API.replace(/^http/, "ws") : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`;

export type Layer =
  | "lower_third" | "stat_panel" | "heatmap" | "ticker"
  | "full_screen" | "caption" | "player_tag" | "pitch_overlay";

export type ProposalStatus =
  | "proposed" | "approved" | "held" | "overridden" | "rejected" | "aired" | "expired";

export type Persona = "newcomer" | "fan" | "analyst";
export type Access = "none" | "deaf";
export type Lang = "en" | "es" | "hi";
export type Allegiance = "home" | "away" | "neutral";

export type EvidenceLine = { event_id: string; text: string };
export type Alternative = { layer: Layer; line: string; rejected_because: string };
export type HoldAdvice = { recommend_hold: boolean; reason?: string | null; until_play_ms?: number | null };
export type AgentMeta = { routing: string; model_served?: string | null; latency_ms?: number | null };

export type Proposal = {
  proposal_id: string;
  cue_id: string;
  match_id: string;
  moment_id: string;
  layer: Layer;
  // Scheduling, assigned by scheduler.py on play time
  t_in_ms: number;
  t_out_ms: number;
  priority: number;
  replaces: string[];
  min_hold_ms: number;
  max_delay_ms: number;
  // Display timing for the operator
  t_start_ms: number;
  t_end_ms: number;
  // Content
  line: string;
  payload: Record<string, unknown> & { intel?: MomentMetrics | null };
  reasoning: string;
  alternatives: Alternative[];
  evidence: EvidenceLine[];
  hold_advice: HoldAdvice;
  faithfulness: number | null;
  fallback: boolean;
  // Decision
  status: ProposalStatus;
  decided_by: string | null;
  decided_at: string | null;
  override_line: string | null;
  meta: AgentMeta;
  // Timing and packages
  proposed_at?: string | null;
  proposed_play_ms?: number | null;
  warn_at?: string | null;
  hold_at?: string | null;
  package_id?: string | null;
  package_seq?: number | null;
  package_offset_ms?: number | null;
  item_label?: string | null;
  /** Numbers on the English line that are not in the moment's facts. Non-empty means flag it amber. */
  unsourced_numbers?: string[] | null;
};

export type MomentMsg = {
  moment: {
    moment_id: string; t_ms: number; play_ms?: number; period: number; kind: string;
    importance: number; summary: string; beat?: "chance" | "result" | "none";
    metrics?: MomentMetrics | null;
  };
  explanation: { headline: string; why_it_matters: string; pattern: string; cites: string[]; confidence: number };
  line: string;
  failures: string[];
  intel?: MomentMetrics | null;
};

/** One viewer group's outcome for one approval: what they got and why. */
export type DeliveryAudit = {
  approval_id: string;
  proposal_id: string;
  persona: Persona;
  access: Access;
  lang: Lang;
  source: "variant" | "template" | "base" | "override" | string;
  failures: string[];
};

export type SlaWarning = {
  proposal_id: string;
  package_id?: string | null;
  seconds_left: number;
  hold_at: string;
};

export type PlayClock = { period: number; clock_ms: number; play_ms: number };

/** One row of the append-only decision log. Every action is here, including holds by the timer. */
export type DecisionEntry = {
  entry_id: string;
  match_id?: string;
  proposal_id: string;
  action: string;
  actor: string;
  at: string;
  reasoning?: string | null;
  package_id?: string | null;
};

export type DecideAction = "approve" | "hold" | "override" | "reject";

/** A non-2xx answer from the API, with FastAPI's `detail` pulled out of the JSON body. */
export class ApiError extends Error {
  constructor(readonly status: number, readonly detail: string) {
    super(`${status} ${detail}`);
    this.name = "ApiError";
  }
}

/** `{"detail": "..."}`, or a validation error's list of `{msg}`, as one plain sentence. */
async function detailOf(r: Response): Promise<string> {
  const text = await r.text();
  try {
    const d = JSON.parse(text).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((e) => e?.msg ?? String(e)).join("; ");
  } catch { /* not JSON: use the text as it came */ }
  return text || r.statusText;
}

async function post(path: string, body: Record<string, unknown>) {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new ApiError(r.status, await detailOf(r));
  return r.json();
}

/**
 * What the operator reads when an action fails. `action` says what was being tried, as a verb phrase:
 * "fire the graphic". A 409 means the thing was already decided, by someone else or the timer.
 */
export function errorMessage(err: unknown, action: string): string {
  if (err instanceof ApiError && err.status === 409) return `Couldn't ${action}: ${err.detail}. Nothing was changed.`;
  if (err instanceof ApiError) return `Couldn't ${action}: ${err.detail} (${err.status}).`;
  return `Couldn't ${action}: ${err instanceof Error ? err.message : String(err)}`;
}

/** Decide one graphic. `override_line` is accepted only on override; sending it elsewhere is a 422. */
export async function decide(id: string, action: DecideAction, body: Record<string, unknown> = {}) {
  return post(`/proposals/${id}/${action}`, { actor: "operator", ...body }) as Promise<Proposal>;
}

/** Decide every open item of a goal routine in running order, with one click. */
export async function decidePackage(packageId: string, action: "approve" | "hold" | "reject") {
  return post(`/packages/${packageId}/${action}`, { actor: "operator" }) as Promise<Proposal[]>;
}

/**
 * The demo window: minutes 41 to 46 of the reference match.
 *
 * A big chance saved, the goal that followed it, a free kick in the final third and a second big chance
 * — four decisions, one of them a goal routine. Everything before 41:00 is folded into match state by the
 * API without proposing anything, so the desk joins a match already in progress rather than waiting forty
 * minutes for one, which is also the path a console takes connecting to a live feed mid-match.
 */
export const DEMO_WINDOW = { from_play_ms: 2_460_000, to_play_ms: 2_760_000 };

/**
 * 20x through the dead air, real time for as long as anyone owes an answer.
 *
 * Falling back to 1x on an open decision is the API's default at any speed, so `speed` here only sets how
 * fast the match moves when the running order is clear. The two mitigations compose: the window picks the
 * five minutes worth watching, the decompression skips the gaps inside them, and all four decisions are
 * still taken at the speed the operator would really have.
 */
export type ReplayScope = "window" | "full";

export const startReplay = (scope: ReplayScope = "window", file = "data/reference/match-042.jsonl", speed = 20) =>
  post("/matches/replay", { file, speed, ...(scope === "window" ? DEMO_WINDOW : {}) });

export async function fetchDecisions(): Promise<DecisionEntry[]> {
  const r = await fetch(`${API}/decisions`);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  const body = await r.json();
  return Array.isArray(body) ? body : body.decisions ?? [];
}

export const decisionsCsvUrl = `${API}/decisions.csv`;

/** One of the 54 persona x access x language x side combinations, as the picker lists them. */
export type ViewerGroup = {
  key: string;
  persona: Persona;
  access: Access;
  lang: Lang;
  allegiance: Allegiance;
};

/** "newcomer.deaf.hi.away" as the picker shows it: "hi newcomer · deaf". */
export const viewLabel = (key: string) => {
  const [persona, access, lang] = key.split(".");
  return `${lang} ${persona}${access === "deaf" ? " · deaf" : ""}`;
};

/** What one viewer group would get if this proposal were fired now. Read-only: nothing airs. */
export type PreviewLine = {
  /** The whole group, not its key: `view.key` is what to label and key the row by. */
  view: ViewerGroup;
  text: string;
  source: "variant" | "template" | "base" | "override" | string;
  lang_shown: Lang;
  failures: string[];
  perspective?: Record<string, unknown> | null;
};

export async function fetchViewerGroups(): Promise<ViewerGroup[]> {
  const r = await fetch(`${API}/viewer-groups`);
  if (!r.ok) throw new Error(`${r.status}`);
  const body = await r.json();
  return Array.isArray(body) ? body : body.groups ?? [];
}

/**
 * At most 12 views per the API. `overrideLine` previews typed text before it is fired.
 * The API answers `{proposal_id, override_line, items}` (preview.py `Preview`).
 */
export async function fetchPreview(
  proposalId: string,
  views: string[],
  overrideLine?: string,
): Promise<PreviewLine[]> {
  const qs = new URLSearchParams();
  for (const v of views.slice(0, 12)) qs.append("view", v);
  if (overrideLine) qs.set("override_line", overrideLine);
  const r = await fetch(`${API}/proposals/${proposalId}/preview?${qs}`);
  if (!r.ok) throw new Error(`${r.status}`);
  const body: { items?: PreviewLine[] } = await r.json();
  return body.items ?? [];
}

/** GET /metrics — the three numbers a broadcaster asks for before trusting a tool in the gallery. */
export type GalleryMetrics = {
  turnaround: { fired: number; median_s: number | null; p90_s: number | null; max_s: number | null };
  errors: {
    decided: number;
    overridden: number;
    dropped: number;
    override_rate: number | null;
    drop_rate: number | null;
    fallback_proposals: number;
    deliveries: Record<string, number>;
    check_failures: Record<string, number>;
  };
  workload: {
    operator_decisions: number;
    sla_holds: number;
    expired: number;
    pending: number;
    play_minutes: number;
    decisions_per_10_min: number | null;
    packages_fired: number;
    graphics_per_click: number | null;
  };
};

export async function fetchMetrics(): Promise<GalleryMetrics> {
  const r = await fetch(`${API}/metrics`);
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

export const sourceWord = (s: string) =>
  s === "variant" ? "✓ variant"
    : s === "template" ? "↩ template"
      : s === "override" ? "Override"
        : "↩ English line";

/** Match clock for display: period plus the clock within it. Never use this for ordering. */
export const clock = (ms: number, period: number) =>
  `${String(Math.floor(ms / 60000) + (period === 2 ? 45 : 0)).padStart(2, "0")}:${String(Math.floor((ms % 60000) / 1000)).padStart(2, "0")}`;

/** Play time, which is what everything is scheduled on. Monotonic, so safe to subtract. */
export const playClock = (playMs: number) =>
  `${String(Math.floor(playMs / 60000)).padStart(2, "0")}:${String(Math.floor((playMs % 60000) / 1000)).padStart(2, "0")}`;

/** Layer names as a gallery says them: "Lower third", not "lower_third". */
export const layerName = (l: string) => {
  const s = l.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
};

/** What produced this line: the routed model, or Template when the fallback wrote it. */
export const modelLabel = (p: Pick<Proposal, "fallback" | "meta">) =>
  p.fallback || p.meta?.routing === "template" ? "Template" : p.meta?.model_served ?? null;

export const STATUS_WORDS: Record<string, string> = {
  proposed: "Awaiting decision",
  approved: "Fired",
  overridden: "Overridden",
  held: "Held",
  rejected: "Dropped",
  aired: "On air",
  expired: "Expired",
  sla_held: "Held by the timer",
};

/** Decision-log wording: the actor matters as much as the action. */
export function decisionLabel(status: string, actor?: string | null): string {
  if (actor === "sla-timer" || status === "sla_held") return "Held by the timer";
  if (actor === "expiry-rule") return "Expired";
  return STATUS_WORDS[status] ?? status;
}

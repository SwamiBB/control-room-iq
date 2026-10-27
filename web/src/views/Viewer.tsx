import { useCallback, useEffect, useId, useRef, useState } from "react";
import { WS, fetchStanding, matchMinute, type MatchStanding } from "../api";
import BallPath from "../components/BallPath";
import IntelChips from "../components/IntelChips";
import { PitchLines } from "../components/PitchView";
import TrackingLayer from "../components/TrackingLayer";
import { H, W, asPath, type PathPoint } from "../components/pitchGeometry";
import { asFrame, nextTrail, shotMirror, type TrackingFrame } from "../components/tracking";
import type { IntelRegister, MomentMetrics } from "../intel";
import { BUG_RECT, LAYER_RECTS, layerOf, onScreen, rectStyle, type Layer } from "../layout";
import { HEADINGS, chanceText, heading, outcomeText, zoneText } from "../labels";
import { useLiveSocket } from "../useLiveSocket";
import { SHOT_ON_SCREEN_MS, useRecent } from "../useRecent";
import "./viewer.css";

type Persona = "newcomer" | "fan" | "analyst";
export type Access = "none" | "deaf";
type Allegiance = "home" | "away" | "neutral";
type Lang = "en" | "es" | "hi";

const PERSONAS: Record<Persona, string> = { newcomer: "New to football", fan: "Fan", analyst: "Analyst" };
const ACCESS: Record<Access, string> = { none: "Standard", deaf: "Deaf — cues and captions" };

/** What each choice changes, for the pickers' tooltips: the personalizer agent's rules, in a viewer's words. */
export const PERSONA_HELP: Record<Persona, string> = {
  newcomer: "Plain words, no jargon. Says what happened rather than the statistic, with one fact at most.",
  fan: "Knows the game. Warm, factual lines with a key number or two, rounded: a speed, a pass length.",
  analyst: "Precise and neutral. The supporting figure in full: speeds to one decimal, pass difficulty and accuracy.",
};
export const ACCESS_HELP: Record<Access, string> = {
  none: "The graphics as broadcast.",
  deaf: "A visual cue on every strike, and a caption card with who, where, the outcome and the score. "
    + "Lines never rely on sound.",
};
const LANGS: Record<Lang, string> = { en: "English", es: "Español", hi: "हिन्दी" };
const SIDES: Record<Allegiance, string> = { home: "Home", away: "Away", neutral: "Neutral" };

type Perspective = {
  side?: Allegiance;
  team?: string;
  color?: string;
  score?: [number, number];
  score_text?: string;
};

type FanDetail = {
  shooter?: string | null;
  zone?: string | null;
  outcome?: string | null;
  chance_quality?: string | null;
  xg?: number | null;
  score?: string | null;
};

export type FanCard = {
  card_id: string;
  beat: "chance" | "result" | "none";
  caption: string;
  detail: FanDetail;
  context?: { past?: string | null; now?: string | null; next?: string | null };
  hold_ms: number;
};

export type Packet = {
  cue_id: string;
  match_id: string;
  layer: string;
  line: string;
  lang: Lang;
  access: Access;
  profile: Persona;
  allegiance: Allegiance;
  verified: boolean;
  fallback: boolean;
  /** The packet's slot in play time (packets.py packet_slot). Its length is how long the graphic stays up. */
  t_in_ms: number;
  t_out_ms: number;
  priority: number;
  /** A floor for collisions, not the duration: it defaults to 4000 for every layer. */
  min_hold_ms: number;
  replaces: string[];
  approval_id?: string;
  approved_by?: string;
  approved_at?: string;
  payload?: {
    intel?: MomentMetrics | null;
    perspective?: Perspective;
    names?: Record<string, string>;
    /** [home, away] on the goal routine's ticker (goal_package.py). */
    score?: [number, number];
  };
  fan_card?: FanCard | null;
};

export type Cue = {
  cue_id: string;
  kind: "chance" | "goal" | "whistle" | "crowd_rising" | "crowd_roar" | "crowd_groan" | "card";
  team?: string | null;
  direction?: "left_to_right" | "right_to_left" | null;
  crowd_level: number;
  pulse: "tap" | "pulse" | "wave" | "surge";
  hold_ms: number;
};

export type Held = { packet: Packet; arrivedAt: number; until: number };

const MIN_ON_SCREEN_MS = 2000;
/**
 * The longest any layer stays up, whatever its slot says: the agents' per-layer maximum (MAX_SLOT_MS in
 * services/agents/agents/workflow.py), and 45 s for the goal routine's code-built ticker. A guard for any
 * other source of packets, so a bad slot cannot pin a graphic on screen.
 */
const MAX_ON_SCREEN_MS: Record<string, number> = {
  lower_third: 12_000, stat_panel: 20_000, heatmap: 20_000, full_screen: 25_000, ticker: 45_000, default: 45_000,
};

/**
 * How long a packet stays on screen: its slot, or its caption card's hold if that is longer.
 *
 * The slot is play time and this socket has no match clock, so its length is spent in real time from
 * arrival. Not min_hold_ms: that is 4000 on every packet, which would cut the 45 s goal ticker and the
 * 8 s caption card short.
 */
export function holdMs(p: Packet): number {
  const slot = p.t_out_ms - p.t_in_ms;
  const wanted = Math.max(Number.isFinite(slot) ? slot : 0, p.fan_card?.hold_ms ?? 0, MIN_ON_SCREEN_MS);
  return Math.min(wanted, MAX_ON_SCREEN_MS[p.layer] ?? MAX_ON_SCREEN_MS.default);
}

/** Adds a packet. A re-send under the same cue_id replaces it; a packet supersedes the ids it names. */
export function withPacket(held: Map<string, Held>, packet: Packet, now: number): Map<string, Held> {
  const next = new Map(held);
  for (const id of packet.replaces ?? []) next.delete(id);
  next.set(packet.cue_id, { packet, arrivedAt: now, until: now + holdMs(packet) });
  return next;
}

/** What is still up at `now`, newest first. */
export function liveAt(held: Map<string, Held>, now: number): Held[] {
  return [...held.values()].filter((h) => h.until > now).sort((a, b) => b.arrivedAt - a.arrivedAt);
}

/**
 * What goes in the main slot, from `live` (newest first).
 *
 * The caption layer never queues: a new line always cuts the running one. Otherwise the newest graphic
 * wins, except that a ticker never displaces anything else. A goal routine's three packets arrive in the
 * same instant when fired, and a newest-wins ticker would take the slot from the lead graphic, which is the
 * one carrying the deaf fan's caption card.
 *
 * Arrival order is all this can go on. The routine's timing (package_offset_ms, t_in_ms) is play time and
 * this socket has no match clock; spending it as real time would put the scorer stats 25 real seconds after
 * the goal while the match, at replay speed, has moved minutes on. So nothing here delays a packet.
 */
export function mainSlot(live: Held[]): Held | undefined {
  return live.find((h) => h.packet.layer === "caption")
    ?? live.find((h) => h.packet.layer !== "caption" && h.packet.layer !== "ticker")
    ?? live.find((h) => h.packet.layer === "ticker");
}

/** Drops what has expired. Returns the same map when nothing has, so an idle tick does not re-render. */
export function pruneExpired(held: Map<string, Held>, now: number): Map<string, Held> {
  if ([...held.values()].every((h) => h.until > now)) return held;
  return new Map([...held].filter(([, h]) => h.until > now));
}

/**
 * The facts under the caption. Every value is the stats engine's; only the labels are translated,
 * and names are never translated. Empty context is hidden rather than shown blank.
 */
function CaptionCard({ card, lang }: { card: FanCard; lang: Lang }) {
  const d = card.detail ?? {};
  const rows: Array<[string, string]> = [];
  if (d.shooter) rows.push([heading("shooter", lang), d.shooter]);
  const zone = zoneText(d.zone, lang);
  if (zone) rows.push([heading("zone", lang), zone]);
  const outcome = outcomeText(d.outcome, lang);
  if (outcome) rows.push([heading("outcome", lang), outcome]);
  const chance = chanceText(d.xg, d.chance_quality, lang);
  if (chance) rows.push([heading("chance", lang), chance]);
  if (d.score) rows.push([heading("score", lang), d.score]);
  if (rows.length === 0) return null;

  return (
    <dl className="caption-card" data-kicker={heading("caption", lang)}>
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * The score bug, top left: team codes with a side chip, the score, the clock in the red tally block. It is
 * the stats engine's own count and clock (GET /state), so it needs no approval, and it is the one thing on
 * the frame that is always there.
 */
function ScoreBug({ standing, lang }: { standing: MatchStanding | null; lang: Lang }) {
  const minute = standing ? matchMinute(standing.period, standing.clockMs) : null;
  const place = { top: `${BUG_RECT.top}%`, left: `${BUG_RECT.left}%`, maxWidth: `${BUG_RECT.width}%` };
  return (
    <div className="score-bug" style={place} aria-label={standing ? "Score and match clock" : undefined}>
      {standing ? (
        <>
          <span className="team"><i className="chip home" />{(standing.homeTeam ?? "Home").toUpperCase()}</span>
          <span className="score">{standing.home}–{standing.away}</span>
          <span className="team"><i className="chip away" />{(standing.awayTeam ?? "Away").toUpperCase()}</span>
          <span className="clock">{minute ?? heading("live", lang)}</span>
        </>
      ) : (
        <span className="clock waiting">{heading("waiting", lang)}</span>
      )}
    </div>
  );
}

/**
 * One graphic as furniture: kicker, main line, detail. The overlay around it is only the layer's region;
 * this is the object drawn in it, sized to its content.
 */
function Graphic({ p, layer, lang, register }: { p: Packet; layer: Layer; lang: Lang; register: IntelRegister }) {
  // No badge for a template line: it is built from the official data, and the operator console already marks
  // it Template before it airs. A viewer has nothing to do with that information.
  const badges = (!p.verified || p.lang !== lang) && (
    <span className="badges">
      {!p.verified && <span className="badge override">{heading("unverified", lang)}</span>}
      {p.lang !== lang && <span className="badge lang">{heading("in_english", lang)}</span>}
    </span>
  );
  const kicker = kickerFor(p, lang);
  // The main text is the delivered line, never fan_card.caption (that is the English reference).
  if (layer === "ticker") {
    return (
      <div className="gfx">
        <span className="tag">{kicker}</span>
        <span className="main">{p.line}</span>
        {badges}
      </div>
    );
  }
  const detail = layer !== "player_tag" && (
    <IntelChips metrics={p.payload?.intel as MomentMetrics | undefined} name={nameLookup(p)} register={register}
                lang={lang} />
  );
  // The spine takes the team colour the graphic carries (the scorer's stats do), else the viewer's side.
  const teamColor = (p.payload as { team_color?: unknown } | undefined)?.team_color;
  const spine = typeof teamColor === "string" ? { background: teamColor } : undefined;
  return (
    <div className="gfx">
      {layer === "lower_third" && <span className="spine" style={spine} aria-hidden="true" />}
      <div className="body">
        <span className="kick">{kicker}{badges}</span>
        <span className="main">{p.line}</span>
        {detail && <div className="detail">{detail}</div>}
      </div>
    </div>
  );
}

/**
 * The caption card for this viewer, if any. It rides on the lead graphic only, on a result beat, and it is
 * for deaf-access viewers only: the API sends the same packet to every viewer, card included, so the
 * renderer is where a hearing viewer's copy is left out.
 */
export function captionCardFor(packet: Packet | undefined, access: Access): FanCard | null {
  return access === "deaf" ? packet?.fan_card ?? null : null;
}

/**
 * Player id to display name, for the chips. The agents put the names beside the numbers they belong to, in
 * `payload.intel.names`; `payload.names` is kept as a fallback. An id with no name is shown as the id.
 */
export function nameLookup(packet: Packet | undefined): (id?: string | null) => string {
  const names = packet?.payload?.intel?.names ?? packet?.payload?.names ?? {};
  return (id) => (id ? names[id] ?? id : "");
}

/**
 * The score this packet tells the viewer, if any: a supporter's own framing first ("winning 1–0"), then the
 * caption card's, then the ticker's [home, away]. A neutral viewer gets no framing from the API, so before the
 * first card or ticker there is nothing to show.
 */
export function scoreText(packet: Packet): string | null {
  const score = packet.payload?.score;
  return packet.payload?.perspective?.score_text
    ?? packet.fan_card?.detail?.score
    ?? (Array.isArray(score) && score.length === 2 ? `${score[0]}–${score[1]}` : null);
}

/**
 * Within one run a packet can start at most a package offset (25 s, goal_package.py) before one already seen,
 * since every packet's slot is the play time it was fired at plus its offset. A rerun jumps back minutes.
 */
const RERUN_MS = 60_000;

/** The latest shot's path, for the pitch behind the graphics: points as the stats engine sent them. */
export type StripShot = { points: PathPoint[]; player?: string | null; name?: string };

/** The live strip and the pitch's latest shot, and the match they belong to. */
export type Strip = { matchId: string; latestMs: number; score?: string; color?: string; shot?: StripShot };

/** The packet's own shot path, if the stats engine sent one: never built from anything else. */
export function shotOf(packet: Packet): StripShot | null {
  const intel = packet.payload?.intel;
  const points = asPath(intel?.shot_path);
  if (!points) return null;
  const player = intel?.player ?? null;
  const name = player ? intel?.names?.[player] ?? packet.payload?.names?.[player] : undefined;
  return { points, player, ...(name ? { name } : {}) };
}

/**
 * The strip after a packet. It keeps the last score any packet of this match gave. A packet for another
 * match_id, or from well back in play time (Run again reuses the match_id), starts over at "–". The viewer
 * socket gets no match message, so the packets are all there is to tell.
 */
export function nextStrip(prev: Strip | null, packet: Packet): Strip {
  const same = prev !== null && prev.matchId === packet.match_id && packet.t_in_ms > prev.latestMs - RERUN_MS;
  const base = same ? prev : null;
  const score = scoreText(packet);
  return {
    matchId: packet.match_id,
    latestMs: Math.max(base?.latestMs ?? packet.t_in_ms, packet.t_in_ms),
    ...(score ? { score, color: packet.payload?.perspective?.color } : { score: base?.score, color: base?.color }),
    shot: shotOf(packet) ?? base?.shot,
  };
}

/**
 * The strip after GET /state on connect: the score as the stats engine has it, so a refreshed screen shows it
 * at once rather than "–" until the next scored graphic. A packet's own framing for this run already on the
 * strip is kept ("winning 1–0" beats a neutral "1–0"); another match, or a rerun, starts over from the count.
 */
export function withStanding(prev: Strip | null, s: MatchStanding): Strip {
  const same = prev !== null && prev.matchId === s.matchId && s.playMs > prev.latestMs - RERUN_MS;
  if (same && prev.score) return { ...prev, latestMs: Math.max(prev.latestMs, s.playMs) };
  return {
    matchId: s.matchId,
    latestMs: Math.max(same ? prev.latestMs : s.playMs, s.playMs),
    score: `${s.home}–${s.away}`,
    ...(same && prev.shot ? { shot: prev.shot } : {}),
  };
}

/**
 * Has a new run started since the last standing? The viewer socket sends no match frame, so the poll of GET
 * /state is how this screen finds out: the match gone (the API is loading the next run), another match, or play
 * time gone back at all (Run again of the same match). Within a run the stats engine's play time only moves on,
 * so unlike a packet's time, which a late arrival can put behind, any step back is a new run.
 */
export function isRestart(prev: MatchStanding | null, next: MatchStanding | null): boolean {
  if (!prev) return false;
  if (!next) return true;
  return next.matchId !== prev.matchId || next.playMs < prev.playMs;
}

/** The standalone viewer's choices from its URL, so a refresh brings back the same viewer. Unknown values are ignored. */
export function settingsFromQuery(search: string): ViewerPreset {
  const q = new URLSearchParams(search);
  const pick = <K extends string>(key: string, allowed: Record<K, string>): K | undefined => {
    const v = q.get(key);
    return v !== null && v in allowed ? (v as K) : undefined;
  };
  return {
    persona: pick("persona", PERSONAS),
    access: pick("access", ACCESS),
    lang: pick("lang", LANGS),
    allegiance: pick("allegiance", SIDES),
  };
}

export const queryFor = (s: Required<ViewerPreset>) =>
  new URLSearchParams({ persona: s.persona, access: s.access, lang: s.lang, allegiance: s.allegiance }).toString();

/**
 * The small line above a graphic's main text, from what the packet already carries: what happened (the
 * caption card's outcome), the score (the goal ticker), the official stats (the scorer's lower third), a
 * shot, or else the layer's own word. Never generated text.
 */
export function kickerFor(p: Packet, lang: Lang): string {
  const outcome = outcomeText(p.fan_card?.detail?.outcome, lang);
  if (outcome) return outcome;
  const payload = p.payload as (Packet["payload"] & { source?: string }) | undefined;
  if (Array.isArray(payload?.score)) return heading("score", lang);
  if (payload?.source === "code") return heading("stats", lang);
  if (payload?.intel?.shot_speed_kmh != null || payload?.intel?.shot_path) return heading("shot", lang);
  return heading("live", lang);
}

/** The gate, enforced in the renderer: a packet with no approval cannot be drawn. */
export function isApproved(p: Packet): boolean {
  return Boolean(p.approval_id && p.approved_by && p.approved_at);
}

/**
 * The strike cue's lifetime. show() puts a cue up for its hold_ms, cutting any running one; clear() takes
 * it down at once, which is what a change of settings needs: clearing only the timer left the cue up for good.
 */
export function cueTimer(setCue: (c: Cue | null) => void) {
  let t: ReturnType<typeof setTimeout> | undefined;
  return {
    show(c: Cue) {
      clearTimeout(t);
      setCue(c);
      t = setTimeout(() => setCue(null), c.hold_ms ?? 1500);
    },
    clear() {
      clearTimeout(t);
      setCue(null);
    },
  };
}

/** The strike cue's one word, in the viewer's language. */
export const cueWord = (kind: string, lang: Lang) => HEADINGS[`cue.${kind}`]?.[lang] ?? heading("cue.play", lang);

/**
 * A small "?" beside a picker's label: hover or focus it for what every choice means. The select carries the
 * current choice's meaning as its own tooltip too, and points screen readers at this list.
 */
function Help<K extends string>({ id, names, help }: { id: string; names: Record<K, string>; help: Record<K, string> }) {
  return (
    <span className="help" tabIndex={0} aria-label="What these mean">
      ?
      <span className="tip" role="tooltip" id={id}>
        {(Object.keys(names) as K[]).map((k) => <span key={k}><b>{names[k]}</b>: {help[k]}</span>)}
      </span>
    </span>
  );
}

export type ViewerPreset = {
  persona?: Persona;
  access?: Access;
  lang?: Lang;
  allegiance?: Allegiance;
};

type ViewerProps = {
  /** Fix the settings instead of letting the viewer choose. Used by the multiviewer. */
  preset?: ViewerPreset;
  /** false hides the controls and shows the settings as a caption instead. */
  chrome?: boolean;
};

export default function Viewer({ preset, chrome = true }: ViewerProps = {}) {
  // A preset (the multiviewer) fixes the settings; otherwise they come from the URL, so a refresh keeps them.
  const [initial] = useState<ViewerPreset>(() => preset ?? settingsFromQuery(window.location.search));
  const [persona, setPersona] = useState<Persona>(initial.persona ?? "fan");
  const [access, setAccess] = useState<Access>(initial.access ?? "none");
  const [lang, setLang] = useState<Lang>(initial.lang ?? "en");
  const [allegiance, setAllegiance] = useState<Allegiance>(initial.allegiance ?? "neutral");
  const helpId = useId(); // the multiviewer draws three viewers: their tooltip ids must not collide
  useEffect(() => {
    if (preset) return;
    try {
      window.history.replaceState(null, "", `${window.location.pathname}?${queryFor({ persona, access, lang, allegiance })}`);
    } catch {
      /* a sandboxed frame: the settings just do not survive a refresh */
    }
  }, [preset, persona, access, lang, allegiance]);

  // Packets live in a map keyed by cue_id: a re-send under the same id replaces the one on screen.
  const [held, setHeld] = useState<Map<string, Held>>(new Map());
  const [cue, setCue] = useState<Cue | null>(null);
  const [refused, setRefused] = useState(0);
  const [cues] = useState(() => cueTimer(setCue));
  const [strip, setStrip] = useState<Strip | null>(null);
  const [standing, setStanding] = useState<MatchStanding | null>(null);
  // The players and the ball: the latest frame, the ball's recent frames, and when the latest arrived.
  const [track, setTrack] = useState<{ frame: TrackingFrame; trail: TrackingFrame[]; stepMs: number; at: number } | null>(null);

  // No match clock on this socket, so anchor the hold at arrival: a late packet still gets its time.
  const upsert = useCallback((packet: Packet) => {
    const now = Date.now();
    setHeld((prev) => withPacket(prev, packet, now));
    // The strip outlives the graphics, but not the match: see nextStrip.
    setStrip((prev) => nextStrip(prev, packet));
  }, []);

  const url = `${WS}/ws/viewer?${new URLSearchParams({ persona, access, lang, allegiance })}`;
  const link = useLiveSocket(url, (m: any) => {
    {
      if (m.type === "overlay") {
        const packet = m.item as Packet;
        if (!isApproved(packet)) {
          // Nothing reaches this screen without a human decision behind it.
          console.warn("Renderer refused a packet with no approval fields:", packet.cue_id, packet);
          setRefused((n) => n + 1);
          return;
        }
        upsert(packet);
      }
      if (m.type === "fan_cue") cues.show(m.cue as Cue);
      if (m.type === "tracking") {
        const frame = asFrame(m.frame);
        if (!frame) return;
        const at = Date.now();
        // Each frame is reached over the time since the last one, so the dots glide at any replay speed.
        setTrack((prev) => ({
          frame,
          trail: prev ? nextTrail(prev.trail, frame) : [frame],
          stepMs: prev ? Math.min(400, Math.max(80, at - prev.at)) : 0,
          at,
        }));
      }
    }
  });

  // The viewer socket sends no match frame or clock, so the score bug asks where the match stands: at once on
  // connect (a refresh included), then every 2 s for the clock. No match loaded leaves the bug waiting.
  // A new run takes the last run's graphics and shot down at once, rather than leaving them up until they expire.
  const lastStanding = useRef<MatchStanding | null>(null);
  const [warming, setWarming] = useState(false);
  useEffect(() => {
    if (link !== "live") return;
    let stop = false;
    const ask = () => fetchStanding()
      .then((st) => {
        if (stop) return;
        if (isRestart(lastStanding.current, st)) {
          setHeld(new Map());
          cues.clear();
          setStrip(null);
          setTrack(null);
          setWarming(true);
        }
        if (st) setWarming(false);
        lastStanding.current = st;
        setStanding(st);
        if (st) setStrip((prev) => withStanding(prev, st));
      })
      .catch(() => undefined); // keep the last known standing through a failed poll
    ask();
    const t = window.setInterval(ask, 2000);
    return () => { stop = true; window.clearInterval(t); };
  }, [link, url, cues]);

  // New settings mean a new feed: a cue or graphic from the old one must not outlive it, nor a score worded for
  // another side or language. A graphic is held for up to 45 s, so a viewer switching from Spanish to Hindi kept
  // the Spanish line up, badged "in English" (#59). The next graphic comes in the new language.
  useEffect(() => {
    return () => {
      cues.clear();
      setStrip(null);
      setHeld(new Map());
    };
  }, [persona, access, lang, allegiance, cues]);

  // Expire held packets on a light tick rather than per-packet timers. Dropping them is what re-renders,
  // and `live` is worked out on every render: a memo on `held` alone never saw the clock move.
  useEffect(() => {
    const t = window.setInterval(() => setHeld((prev) => pruneExpired(prev, Date.now())), 500);
    return () => window.clearInterval(t);
  }, []);

  const live = liveAt(held, Date.now());
  // The latest shot's path for a few seconds after it arrives, then the pitch is the players' again.
  const shotUp = useRecent(strip?.shot ? strip.shot.points.join(";") : null, SHOT_ON_SCREEN_MS);

  // Every layer on screen is drawn below. The caption card rides on whichever of them carries it (the goal
  // routine's lead), not on the newest, so the scorer's lower third arriving with it no longer hides the card.
  const shown = onScreen(live);
  const packet = shown.find((h) => h.packet.fan_card)?.packet ?? mainSlot(live)?.packet;
  const fullScreenUp = shown.some((h) => layerOf(h.packet.layer) === "full_screen");

  const register: IntelRegister = persona;
  const nameOf = nameLookup(packet);
  const accent = allegiance !== "neutral" ? strip?.color : undefined;
  const card = captionCardFor(packet, access);

  return (
    <div
      className={`viewer viewer-${access}`}
      lang={lang}
      data-lang={lang}
      style={accent ? ({ ["--side-color" as string]: accent }) : undefined}
    >
      <header className="viewer-head">
        {chrome ? <h1>Viewer</h1> : (
          <p className="frame-label">
            {PERSONAS[persona]} · {ACCESS[access]} · {LANGS[lang]}
            {allegiance !== "neutral" && ` · ${SIDES[allegiance]}`}
          </p>
        )}
        <div className="viewer-controls" hidden={!chrome}>
          <label>
            <span>Who is watching <Help id={`${helpId}-persona`} names={PERSONAS} help={PERSONA_HELP} /></span>
            <select value={persona} onChange={(e) => setPersona(e.target.value as Persona)}
                    title={PERSONA_HELP[persona]} aria-describedby={`${helpId}-persona`}>
              {Object.entries(PERSONAS).map(([k, v]) => (
                <option key={k} value={k} title={PERSONA_HELP[k as Persona]}>{v}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Accessibility <Help id={`${helpId}-access`} names={ACCESS} help={ACCESS_HELP} /></span>
            <select value={access} onChange={(e) => setAccess(e.target.value as Access)}
                    title={ACCESS_HELP[access]} aria-describedby={`${helpId}-access`}>
              {Object.entries(ACCESS).map(([k, v]) => (
                <option key={k} value={k} title={ACCESS_HELP[k as Access]}>{v}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Language</span>
            <select value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
              {Object.entries(LANGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label>
            <span>Supporting</span>
            <select value={allegiance} onChange={(e) => setAllegiance(e.target.value as Allegiance)}>
              {Object.entries(SIDES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        </div>
      </header>

      <div className={`pitch ${fullScreenUp ? "full-screen-up" : ""}`}>
        {/* Behind the graphics: the markings, the players and the ball, and the latest shot from where it was struck
            to where it finished. */}
        <svg className="viewer-pitch" viewBox={`-2 -2 ${W + 4} ${H + 4}`} preserveAspectRatio="xMidYMid slice"
             role="img" aria-label={strip?.shot && shotUp ? "Pitch with the latest shot" : track ? "Pitch with the players" : "Pitch"}>
          <PitchLines />
          {track && (
            <TrackingLayer frame={track.frame} trail={track.trail.slice(0, -1)} homeTeam={standing?.homeTeam}
                           stepMs={track.stepMs} />
          )}
          {strip?.shot && shotUp && (
            <BallPath key={strip.shot.points.join(";")} points={strip.shot.points} animate
                      mirror={shotMirror(strip.shot.player, standing?.homeTeam, standing?.period)}
                      label={`${heading("shooter", lang)} ${strip.shot.name ?? nameOf(strip.shot.player)}`.trim()} />
          )}
        </svg>
        {/* Graded like a camera feed: a vignette gives the frame a centre; a full screen dims the whole frame. */}
        <div className="vignette" aria-hidden="true" />
        {fullScreenUp && <div className="scrim" aria-hidden="true" />}
        <ScoreBug standing={standing} lang={lang} />
        {/* Beat one: code-built, no generated text, so it needs no approval and lands on the strike. */}
        {cue && (
          <div
            className={`fan-cue cue-${cue.pulse} ${cue.direction === "right_to_left" ? "edge-left" : "edge-right"}`}
            style={{ ["--level" as string]: String(Math.max(0.15, Math.min(1, cue.crowd_level ?? 0))) }}
            role="status"
            aria-live="assertive"
          >
            <span className="cue-word">{cueWord(cue.kind, lang)}</span>
          </div>
        )}

        {/* Beat two: generated captions, only ever inside approved packets, each layer in its own place. */}
        {shown.map(({ packet: p }) => {
          const layer = layerOf(p.layer);
          return (
            <div key={p.cue_id} className={`overlay layer-${layer}`} style={rectStyle(LAYER_RECTS[layer])}>
              <Graphic p={p} layer={layer} lang={lang} register={register} />
            </div>
          );
        })}

        {/* A feed says nothing between graphics: the pitch carries the picture. Only the link's state, or a
            new run loading, is worth a line. */}
        {shown.length === 0 && !cue && (link !== "live" || warming) && (
          <p className="viewer-idle">
            {link === "live"
              ? "Warming up: the next run is loading."
              : link === "connecting"
                ? "Connecting…"
                : "Lost the feed. Reconnecting automatically."}
          </p>
        )}
      </div>

      {/* The facts sit under the picture, not over it: the caption is the graphic, this is the detail. */}
      {card && <CaptionCard card={card} lang={lang} />}

      {access !== "deaf" && (
        <p className="viewer-note">
          Strike cues and detail cards go to deaf-access viewers. Switch Accessibility to see them.
        </p>
      )}

      <ul className="history">
        {/* Still live but not on screen: an older graphic on a busy layer, or a panel waiting under a full screen. */}
        {live.filter((h) => !shown.includes(h)).map((h) => (
          <li key={h.packet.cue_id}>{h.packet.line}</li>
        ))}
      </ul>

      {refused > 0 && (
        <p className="refused" title="Packets arriving without approval_id / approved_by / approved_at">
          {refused} unapproved {refused === 1 ? "packet" : "packets"} refused by the renderer
        </p>
      )}
    </div>
  );
}

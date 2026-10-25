import { useCallback, useEffect, useRef, useState } from "react";
import { WS } from "../api";
import IntelChips from "../components/IntelChips";
import type { IntelRegister, MomentMetrics } from "../intel";
import { chanceText, heading, outcomeText, zoneText } from "../labels";
import { useLiveSocket } from "../useLiveSocket";
import "./viewer.css";

type Persona = "newcomer" | "fan" | "analyst";
type Access = "none" | "deaf";
type Allegiance = "home" | "away" | "neutral";
type Lang = "en" | "es" | "hi";

const PERSONAS: Record<Persona, string> = { newcomer: "New to football", fan: "Fan", analyst: "Analyst" };
const ACCESS: Record<Access, string> = { none: "Standard", deaf: "Deaf — cues and captions" };
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

type FanCard = {
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
  payload?: { intel?: MomentMetrics | null; perspective?: Perspective; names?: Record<string, string> };
  fan_card?: FanCard | null;
};

type Cue = {
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
 * How long a packet stays on screen: its slot, or its caption card's hold if that is longer.
 *
 * The slot is play time and this socket has no match clock, so its length is spent in real time from
 * arrival. Not min_hold_ms: that is 4000 on every packet, which would cut the 45 s goal ticker and the
 * 8 s caption card short.
 */
export function holdMs(p: Packet): number {
  const slot = p.t_out_ms - p.t_in_ms;
  return Math.max(Number.isFinite(slot) ? slot : 0, p.fan_card?.hold_ms ?? 0, MIN_ON_SCREEN_MS);
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
    <dl className="caption-card">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** The gate, enforced in the renderer: a packet with no approval cannot be drawn. */
export function isApproved(p: Packet): boolean {
  return Boolean(p.approval_id && p.approved_by && p.approved_at);
}

const CUE_WORDS: Record<Cue["kind"], string> = {
  chance: "Shot",
  goal: "Goal",
  whistle: "Whistle",
  crowd_rising: "Crowd rising",
  crowd_roar: "Crowd roar",
  crowd_groan: "Crowd groan",
  card: "Card",
};

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
  const [persona, setPersona] = useState<Persona>(preset?.persona ?? "fan");
  const [access, setAccess] = useState<Access>(preset?.access ?? "none");
  const [lang, setLang] = useState<Lang>(preset?.lang ?? "en");
  const [allegiance, setAllegiance] = useState<Allegiance>(preset?.allegiance ?? "neutral");

  // Packets live in a map keyed by cue_id: a re-send under the same id replaces the one on screen.
  const [held, setHeld] = useState<Map<string, Held>>(new Map());
  const [cue, setCue] = useState<Cue | null>(null);
  const [refused, setRefused] = useState(0);
  const cueTimer = useRef<number | undefined>(undefined);

  // No match clock on this socket, so anchor the hold at arrival: a late packet still gets its time.
  const upsert = useCallback((packet: Packet) => {
    const now = Date.now();
    setHeld((prev) => withPacket(prev, packet, now));
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
      if (m.type === "fan_cue") {
        const c = m.cue as Cue;
        setCue(c);
        window.clearTimeout(cueTimer.current);
        cueTimer.current = window.setTimeout(() => setCue(null), c.hold_ms ?? 1500);
      }
    }
  });

  useEffect(() => {
    return () => window.clearTimeout(cueTimer.current);
  }, [persona, access, lang, allegiance, upsert]);

  // Expire held packets on a light tick rather than per-packet timers. Dropping them is what re-renders,
  // and `live` is worked out on every render: a memo on `held` alone never saw the clock move.
  useEffect(() => {
    const t = window.setInterval(() => setHeld((prev) => pruneExpired(prev, Date.now())), 500);
    return () => window.clearInterval(t);
  }, []);

  const live = liveAt(held, Date.now());

  // The caption layer never queues: a new line always cuts the running one.
  const caption = live.find((h) => h.packet.layer === "caption");
  const graphic = live.find((h) => h.packet.layer !== "caption");
  const current = caption ?? graphic;
  const packet = current?.packet;

  const register: IntelRegister = persona;
  const names: Record<string, string> = packet?.payload?.names ?? {};
  const nameOf = (id?: string | null) => (id ? names[id] ?? id : "");
  const view = packet?.payload?.perspective;
  const accent = allegiance !== "neutral" ? view?.color : undefined;
  // The caption card rides on the lead graphic only, and only on a result beat.
  const card = packet?.fan_card ?? null;

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
            <span>Who is watching</span>
            <select value={persona} onChange={(e) => setPersona(e.target.value as Persona)}>
              {Object.entries(PERSONAS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label>
            <span>Access</span>
            <select value={access} onChange={(e) => setAccess(e.target.value as Access)}>
              {Object.entries(ACCESS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
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

      {/* Persistent live strip: score and clock stay put, cards come and go (Oct 22 decision). */}
      <div className="live-strip">
        <span className="live-dot" aria-hidden="true" />
        <span className="live-word">{heading("live", lang)}</span>
        <b className="live-score">{view?.score_text ?? card?.detail?.score ?? "–"}</b>
      </div>

      <div className="pitch">
        {/* Beat one: code-built, no generated text, so it needs no approval and lands on the strike. */}
        {cue && (
          <div
            className={`fan-cue cue-${cue.pulse} ${cue.direction === "right_to_left" ? "edge-left" : "edge-right"}`}
            style={{ ["--level" as string]: String(Math.max(0.15, Math.min(1, cue.crowd_level ?? 0))) }}
            role="status"
            aria-live="assertive"
          >
            <span className="cue-word">{CUE_WORDS[cue.kind] ?? "Play"}</span>
          </div>
        )}

        {/* Beat two: generated caption, only ever inside an approved packet. */}
        {packet && (
          <div className={`overlay ${packet.layer}`}>
            {!packet.verified && <span className="badge override">Unverified</span>}
            {packet.fallback && <span className="badge fallback">Template</span>}
            {packet.lang !== lang && <span className="badge lang">in English</span>}
            {/* The caption is the delivered line, never fan_card.caption (that is the English reference). */}
            <p className="line">{packet.line}</p>
            <IntelChips metrics={packet.payload?.intel as MomentMetrics | undefined} name={nameOf} register={register} />
          </div>
        )}

        {!packet && !cue && (
          <p className="viewer-idle">
            {link === "live"
              ? "Waiting for the next approved graphic."
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
          Strike cues and detail cards go to deaf-access viewers. Switch Access to see them.
        </p>
      )}

      <ul className="history">
        {live.slice(1).map((h) => (
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

/**
 * The players and the ball, from the API's tracking messages: the simulator's position stream for the match, 4
 * frames a second, sent to every viewer as the replay plays (services/api/api/tracking_feed.py).
 *
 * Tracking is in screen coordinates, 0-100 on both axes with the ball's height in metres: the home side attacks
 * toward x = 100 in the first half and toward x = 0 in the second. Events, and the shot paths built from them, are
 * relative to the team on the ball instead (attacking toward 100), so a shot is mirrored to sit on the same pitch.
 */
import { H, W } from "./pitchGeometry";

export type TrackingFrame = {
  play_ms: number;
  period: number;
  ball: [number, number, number];
  players: Record<string, [number, number]>;
};

const isPoint = (p: unknown, n: number) => Array.isArray(p) && p.length >= n && p.slice(0, n).every(Number.isFinite);

/** A well-formed frame from untrusted JSON, or null. */
export function asFrame(value: unknown): TrackingFrame | null {
  const f = value as Partial<TrackingFrame> | null;
  if (!f || !Number.isFinite(f.play_ms) || !Number.isFinite(f.period) || !isPoint(f.ball, 3)) return null;
  if (!f.players || typeof f.players !== "object") return null;
  const players = Object.fromEntries(Object.entries(f.players).filter(([, p]) => isPoint(p, 2)));
  return { play_ms: f.play_ms!, period: f.period!, ball: f.ball as TrackingFrame["ball"], players };
}

/** Tracking's 0-100 screen coordinates to the pitch's metres. */
export const toPitch = (x: number, y: number) => ({ cx: (x / 100) * W, cy: (y / 100) * H });

/** "har" from "har-09": player ids carry their team. */
export const teamOf = (playerId: string) => playerId.split("-")[0];

/** 9 from "har-09", or null when the id carries no number. */
export function shirtOf(playerId: string): number | null {
  const n = Number(playerId.split("-").pop());
  return Number.isInteger(n) && n > 0 ? n : null;
}

/**
 * The home team's id: the score bug's, once the standing is known; until then the team listed first, as the
 * tracking file lists the home side first.
 */
export function homeOf(frame: TrackingFrame, homeTeam?: string): string | undefined {
  return homeTeam ?? Object.keys(frame.players).map(teamOf)[0];
}

/**
 * Whether a shot path (relative to the shooting team, attacking toward 100) needs turning 180 degrees to sit on
 * the tracking pitch: once for the away side, once more for the second half, when the ends change.
 */
export function shotMirror(shooter: string | null | undefined, homeTeam: string | undefined, period?: number): boolean {
  const away = Boolean(shooter && homeTeam && teamOf(shooter) !== homeTeam);
  return away !== (period === 2);
}

/**
 * The ball's recent positions, newest last: the last two seconds of play, so the trail is the same length at any
 * replay speed (at 20x the frames arrive seconds apart and there is no trail, only the ball). Play going back
 * means a new run, which starts the trail over.
 */
export const TRAIL_MS = 2000;
export function nextTrail(trail: TrackingFrame[], frame: TrackingFrame): TrackingFrame[] {
  const last = trail[trail.length - 1];
  if (last && frame.play_ms <= last.play_ms) return [frame];
  return [...trail, frame].filter((f) => frame.play_ms - f.play_ms <= TRAIL_MS);
}

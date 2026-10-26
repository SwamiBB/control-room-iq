/**
 * What the console says while a replay runs and the desk has nothing to show for it yet: the stretches where
 * the match looks stuck though it is not.
 *
 * - warming: Start was clicked and no state has come back yet. The API is loading the match and folding the
 *   minutes before the window, which proposes nothing.
 * - writing: the match has dropped to real time with no card on the desk, so agents are writing one.
 * - finishing: state has stopped arriving though the replay is still running. The window is over and the API
 *   is waiting for the last moment's agents before it says the replay is complete.
 */
import { REAL_TIME } from "./api";

export type RunPhase = "warming" | "writing" | "finishing";

/**
 * How long without a state message means the replay loop has stopped. The API publishes state on every event
 * once a quarter second has passed, and the reference match has an event at least every half second of play,
 * so at real time (the slowest a replay runs) state comes every half second at most.
 */
export const STALL_MS = 1500;

/** The writing signal must hold this long: a decision speeds the match up again within one pacing slice. */
export const WRITING_SETTLE_MS = 500;

/**
 * True when the slowdown can only be agents at work. The API drops a replay to real time while a card waits on
 * the desk OR agents are still writing one (`_awaiting_decision()` in services/api/api/main.py, which counts
 * hub.moment_tasks). With no card waiting, the agents are the cause. If that predicate is ever narrowed to
 * proposals alone, the match no longer slows while agents write and this signal never fires, without any error:
 * check here when changing it.
 */
export function agentsWriting(speed: number | null, pace: number | null, waiting: number): boolean {
  return speed === REAL_TIME && pace != null && pace > REAL_TIME && waiting === 0;
}

export type RunSignals = {
  /** Start was clicked and this run has sent no state yet. */
  starting: boolean;
  running: boolean | null;
  /** Wall-clock ms of this run's last state message, or null before its first. */
  lastStateAt: number | null;
  /** Since when agentsWriting() has held, or null. */
  writingSince: number | null;
  now: number;
};

export function runPhase(s: RunSignals): RunPhase | null {
  if (s.starting) return "warming";
  if (!s.running) return null;
  if (s.lastStateAt != null && s.now - s.lastStateAt > STALL_MS) return "finishing";
  if (s.writingSince != null && s.now - s.writingSince >= WRITING_SETTLE_MS) return "writing";
  return null;
}

export const RUN_PHASE_TEXT: Record<RunPhase, string> = {
  warming: "Warming up: loading the match…",
  writing: "Agents writing a card…",
  finishing: "Window over. Agents finishing the last card…",
};

/**
 * What a (re)connect does to the console's desk (#52).
 *
 * On every connect the operator socket re-sends the match, as its first frame when there is one, and the
 * proposals. Nothing else comes again: moments, SLA warnings (sent once each), the score and clock, and
 * how the last replay ended. So a connect drops only the proposals. The rest goes only when the connect
 * shows the match is gone (no match frame) or changed (another match_id), as after an API restart.
 */

/** The match is the first frame on connect; none in this long means the API has no match. */
export const RESYNC_GRACE_MS = 2000;

export type DeskClearing = {
  /** What the API re-sends on every connect. */
  proposals: () => void;
  /** Everything that belongs to one match. */
  desk: () => void;
};

export class Resync {
  private pending = false;
  private timer: ReturnType<typeof setTimeout> | undefined;

  constructor(private clear: DeskClearing, private graceMs = RESYNC_GRACE_MS) {}

  /** The socket opened: the proposals are on their way again; the rest waits on the match frame. */
  opened(): void {
    this.clear.proposals();
    this.pending = true;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      if (!this.pending) return;
      this.pending = false;
      this.clear.desk();
    }, this.graceMs);
  }

  /**
   * A match frame. True when it is the desk's own match re-sent on connect, which keeps the desk. Any
   * other match frame is a fresh match, Run again of the same file included, and clears it.
   */
  match(matchId: string | null | undefined, shownId: string | null | undefined): boolean {
    const resent = this.pending;
    this.pending = false;
    clearTimeout(this.timer);
    const same = resent && Boolean(shownId) && shownId === matchId;
    if (!same) this.clear.desk();
    return same;
  }

  dispose(): void {
    this.pending = false;
    clearTimeout(this.timer);
  }
}

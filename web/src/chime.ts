/**
 * A short two-note chime for a new graphic on the desk. No audio file to ship or fail to load.
 *
 * Browsers only let a page make sound after the user has interacted with it, so `prime` is called from
 * the click that turns the alert on; until then a chime is silently skipped rather than an error.
 */

let ctx: AudioContext | null = null;
let last = 0;

export function primeChime(): void {
  try {
    ctx ??= new AudioContext();
    void ctx.resume();
  } catch {
    ctx = null;
  }
}

export function chime(): void {
  const now = Date.now();
  // A goal routine lands as three graphics in a burst: one chime for the burst.
  if (now - last < 600) return;
  last = now;
  try {
    ctx ??= new AudioContext();
    if (ctx.state !== "running") return;
    const t = ctx.currentTime;
    for (const [i, freq] of [880, 1320].entries()) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, t + i * 0.12);
      gain.gain.exponentialRampToValueAtTime(0.15, t + i * 0.12 + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + i * 0.12 + 0.2);
      osc.connect(gain).connect(ctx.destination);
      osc.start(t + i * 0.12);
      osc.stop(t + i * 0.12 + 0.22);
    }
  } catch {
    /* no audio on this machine: the card still arrives */
  }
}

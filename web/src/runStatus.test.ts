import { describe, expect, it } from "vitest";
import { agentsWriting, runPhase, STALL_MS, WRITING_SETTLE_MS, type RunSignals } from "./runStatus";

const base: RunSignals = { starting: false, running: true, lastStateAt: 10_000, writingSince: null, now: 10_200 };

describe("agentsWriting", () => {
  it("is the real-time fallback with no card waiting", () => {
    expect(agentsWriting(1, 20, 0)).toBe(true);
  });

  it("is not a card waiting on the desk, which slows the match too", () => {
    expect(agentsWriting(1, 20, 1)).toBe(false);
  });

  it("cannot tell at real-time pace, nor at the asked-for speed", () => {
    expect(agentsWriting(1, 1, 0)).toBe(false);
    expect(agentsWriting(20, 20, 0)).toBe(false);
  });

  it("stays quiet on a console that never saw the run start", () => {
    expect(agentsWriting(1, null, 0)).toBe(false);
  });
});

describe("runPhase", () => {
  it("warms up from the click until the run's first state", () => {
    expect(runPhase({ ...base, starting: true, running: null, lastStateAt: null })).toBe("warming");
  });

  it("says nothing while state flows and nobody is writing", () => {
    expect(runPhase(base)).toBeNull();
  });

  it("calls a gap in state after the window the last card being finished, at any speed", () => {
    expect(runPhase({ ...base, now: base.lastStateAt! + STALL_MS + 1 })).toBe("finishing");
    expect(runPhase({ ...base, now: base.lastStateAt! + STALL_MS })).toBeNull();
  });

  it("shows agents writing only once the slowdown has held", () => {
    expect(runPhase({ ...base, writingSince: base.now - WRITING_SETTLE_MS })).toBe("writing");
    expect(runPhase({ ...base, writingSince: base.now - WRITING_SETTLE_MS + 100 })).toBeNull();
  });

  it("says nothing once the replay is over", () => {
    expect(runPhase({ ...base, running: false, now: base.lastStateAt! + 60_000 })).toBeNull();
  });
});

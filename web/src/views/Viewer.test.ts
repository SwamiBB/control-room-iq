import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { holdMs, isApproved, liveAt, pruneExpired, withPacket, type Held, type Packet } from "./Viewer";

// The renderer's half of the gate: no approval fields, no drawing.
const approved: Packet = {
  cue_id: "c-1",
  match_id: "m-1",
  layer: "lower_third",
  line: "Big chance for Oli Stone.",
  lang: "en",
  access: "none",
  profile: "fan",
  allegiance: "neutral",
  verified: true,
  fallback: false,
  t_in_ms: 2_520_000,
  t_out_ms: 2_526_000,
  priority: 3,
  min_hold_ms: 4000,
  replaces: [],
  approval_id: "a-1",
  approved_by: "operator",
  approved_at: "2026-10-24T12:00:00Z",
};

describe("isApproved (the gate)", () => {
  it("accepts a packet with approval_id, approved_by and approved_at", () => {
    expect(isApproved(approved)).toBe(true);
  });

  it("refuses a packet missing approval_id", () => {
    const { approval_id: _, ...p } = approved;
    expect(isApproved(p)).toBe(false);
  });

  it("refuses a packet missing approved_by", () => {
    const { approved_by: _, ...p } = approved;
    expect(isApproved(p)).toBe(false);
  });

  it("refuses a packet missing approved_at", () => {
    const { approved_at: _, ...p } = approved;
    expect(isApproved(p)).toBe(false);
  });

  it("refuses a packet with an empty-string approval_id", () => {
    expect(isApproved({ ...approved, approval_id: "" })).toBe(false);
  });
});

// Goal routine, as packets.py builds it: the lead carries the caption card, the ticker runs 45 s.
const card = {
  card_id: "fc-1", beat: "result" as const, caption: "Goal! Oli Stone scores.", detail: {}, hold_ms: 8000,
};
const lead: Packet = { ...approved, cue_id: "c-lead", layer: "full_screen", fan_card: card };
const ticker: Packet = {
  ...approved, cue_id: "c-ticker", layer: "ticker", line: "GOAL 43' · Rivertown 1–0 Harbour · Oli Stone",
  t_in_ms: 2_520_000, t_out_ms: 2_565_000,
};

describe("holdMs", () => {
  it("is the slot's length, not min_hold_ms", () => {
    expect(holdMs(ticker)).toBe(45_000);
  });

  it("is the caption card's hold when that is longer than the slot", () => {
    expect(holdMs(lead)).toBe(8000);
  });

  it("never drops below two seconds, even for an empty slot", () => {
    expect(holdMs({ ...approved, t_out_ms: approved.t_in_ms })).toBe(2000);
  });
});

describe("expiry on the viewer's tick", () => {
  let held: Map<string, Held>;
  let tick: ReturnType<typeof setInterval>;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
    held = new Map();
    // The component's own loop: prune every 500 ms, work out what is live on each render.
    tick = setInterval(() => { held = pruneExpired(held, Date.now()); }, 500);
  });

  afterEach(() => {
    clearInterval(tick);
    vi.useRealTimers();
  });

  it("takes a graphic down when its time is up, leaving nothing held", () => {
    held = withPacket(held, approved, Date.now()); // 6 s slot

    vi.advanceTimersByTime(5_500);
    expect(liveAt(held, Date.now()).map((h) => h.packet.cue_id)).toEqual(["c-1"]);

    vi.advanceTimersByTime(1_000);
    expect(liveAt(held, Date.now())).toEqual([]);
    expect(held.size).toBe(0);
  });

  it("keeps the caption card up for its 8 s and the ticker for its 45 s", () => {
    held = withPacket(held, lead, Date.now());
    held = withPacket(held, ticker, Date.now());

    vi.advanceTimersByTime(7_500);
    expect(liveAt(held, Date.now()).map((h) => h.packet.cue_id).sort()).toEqual(["c-lead", "c-ticker"]);

    vi.advanceTimersByTime(1_000);
    expect(liveAt(held, Date.now()).map((h) => h.packet.cue_id)).toEqual(["c-ticker"]);

    vi.advanceTimersByTime(36_000);
    expect(held.size).toBe(1);
    vi.advanceTimersByTime(1_000);
    expect(held.size).toBe(0);
  });

  it("does not replace the map on a tick where nothing expired", () => {
    held = withPacket(held, ticker, Date.now());
    const before = held;
    vi.advanceTimersByTime(2_000);
    expect(held).toBe(before);
  });
});

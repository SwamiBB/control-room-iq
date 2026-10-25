import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { intelChips } from "../intel";
import { captionCardFor, cueTimer, holdMs, isApproved, liveAt, mainSlot, nameLookup, pruneExpired, withPacket, type Cue, type Held, type Packet } from "./Viewer";

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

describe("mainSlot (goal routine ordering)", () => {
  const at = (packet: Packet, arrivedAt: number): Held => ({ packet, arrivedAt, until: arrivedAt + holdMs(packet) });

  it("keeps the lead graphic when the ticker arrives after it", () => {
    const live = liveAt(new Map([["c-lead", at(lead, 1000)], ["c-ticker", at(ticker, 1001)]]), 1002);
    expect(mainSlot(live)?.packet.cue_id).toBe("c-lead");
    expect(mainSlot(live)?.packet.fan_card?.card_id).toBe("fc-1");
  });

  it("shows the ticker once nothing else is up", () => {
    const live = liveAt(new Map([["c-lead", at(lead, 1000)], ["c-ticker", at(ticker, 1001)]]), 9_500);
    expect(mainSlot(live)?.packet.cue_id).toBe("c-ticker");
  });

  it("still lets a newer non-ticker graphic take the slot", () => {
    const stats: Packet = { ...approved, cue_id: "c-stats", layer: "lower_third" };
    const live = liveAt(new Map([["c-lead", at(lead, 1000)], ["c-stats", at(stats, 1001)]]), 1002);
    expect(mainSlot(live)?.packet.cue_id).toBe("c-stats");
  });

  it("lets a caption cut anything, the ticker included", () => {
    const caption: Packet = { ...approved, cue_id: "c-cap", layer: "caption" };
    const live = liveAt(new Map([["c-cap", at(caption, 1000)], ["c-lead", at(lead, 1001)]]), 1002);
    expect(mainSlot(live)?.packet.cue_id).toBe("c-cap");
  });
});

describe("cueTimer (the strike cue)", () => {
  const shot: Cue = { cue_id: "fc-1", kind: "chance", crowd_level: 0.6, pulse: "pulse", hold_ms: 1500 };

  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("takes the cue down after its hold", () => {
    const setCue = vi.fn();
    cueTimer(setCue).show(shot);
    vi.advanceTimersByTime(1_500);
    expect(setCue.mock.calls).toEqual([[shot], [null]]);
  });

  it("takes the cue down at once on clear, mid-pulse, and does not bring it back", () => {
    const setCue = vi.fn();
    const cues = cueTimer(setCue);
    cues.show(shot);
    vi.advanceTimersByTime(500);

    cues.clear(); // what the settings change runs
    expect(setCue).toHaveBeenLastCalledWith(null);

    vi.advanceTimersByTime(5_000);
    expect(setCue.mock.calls).toEqual([[shot], [null]]);
  });
});

describe("captionCardFor (who gets the caption card)", () => {
  it("gives a deaf-access viewer the lead graphic's card", () => {
    expect(captionCardFor(lead, "deaf")?.card_id).toBe("fc-1");
  });

  it("gives a hearing viewer no card, though the API sent it on their packet", () => {
    expect(lead.fan_card).toBeTruthy();
    expect(captionCardFor(lead, "none")).toBeNull();
  });

  it("gives nobody a card when the packet carries none", () => {
    expect(captionCardFor(ticker, "deaf")).toBeNull();
    expect(captionCardFor(undefined, "deaf")).toBeNull();
  });
});

describe("nameLookup (names in the chips)", () => {
  // payload.intel as match_intel.intel_payload builds it: the names sit beside the ids they belong to.
  const withIntel: Packet = {
    ...approved,
    payload: {
      intel: {
        key_pass: { event_id: "e-9", team: "har", player: "har-06", distance_m: 31, difficulty: 0.7 },
        names: { "har-06": "Oli Stone" },
      },
    },
  };

  it("reads payload.intel.names, so a chip says the player's name and not har-06", () => {
    expect(nameLookup(withIntel)("har-06")).toBe("Oli Stone");
    const chips = intelChips(withIntel.payload?.intel, nameLookup(withIntel), "fan");
    expect(chips[0].label).toBe("Pass by Oli Stone");
  });

  it("falls back to payload.names, then to the id", () => {
    expect(nameLookup({ ...approved, payload: { names: { "riv-09": "Ana Ruiz" } } })("riv-09")).toBe("Ana Ruiz");
    expect(nameLookup(approved)("riv-09")).toBe("riv-09");
    expect(nameLookup(undefined)(null)).toBe("");
  });
});

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { intelChips } from "../intel";
import { ACCESS_HELP, PERSONA_HELP, captionCardFor, cueWord, kickerFor, cueTimer, holdMs, isApproved, isRestart, liveAt, mainSlot, nameLookup, nextStrip, queryFor, scoreText, settingsFromQuery, shotOf, withStanding, pruneExpired, withPacket, type Cue, type Held, type Packet } from "./Viewer";

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

  it("never runs past the layer's longest slot, whatever the packet says (#59)", () => {
    expect(holdMs({ ...approved, t_out_ms: approved.t_in_ms + 600_000 })).toBe(12_000); // a lower third
    expect(holdMs({ ...ticker, t_out_ms: ticker.t_in_ms + 600_000 })).toBe(45_000);
    expect(holdMs({ ...approved, layer: "something_new", t_out_ms: approved.t_in_ms + 600_000 })).toBe(45_000);
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

  it("puts the chip's words in the viewer's language, never the name (#54)", () => {
    const name = nameLookup(withIntel);
    expect(intelChips(withIntel.payload?.intel, name, "fan", "es")[0]).toMatchObject({ label: "Pase de Oli Stone", value: "31 m · Difícil" });
    expect(intelChips(withIntel.payload?.intel, name, "newcomer", "hi")[0]).toMatchObject({ label: "Oli Stone का पास", value: "कठिन पास" });
    expect(intelChips({ shot_speed_kmh: 88.1 }, name, "newcomer", "es")[0]).toMatchObject({ label: "Velocidad del remate", value: "Disparo firme" });
  });

  it("falls back to payload.names, then to the id", () => {
    expect(nameLookup({ ...approved, payload: { names: { "riv-09": "Ana Ruiz" } } })("riv-09")).toBe("Ana Ruiz");
    expect(nameLookup(approved)("riv-09")).toBe("riv-09");
    expect(nameLookup(undefined)(null)).toBe("");
  });
});

describe("scoreText (the live strip)", () => {
  it("prefers a supporter's own framing", () => {
    const home: Packet = { ...approved, payload: { perspective: { side: "home", score_text: "winning 1–0" } } };
    expect(scoreText(home)).toBe("winning 1–0");
  });

  it("gives a neutral viewer the caption card's score, or the ticker's as home–away", () => {
    expect(scoreText({ ...lead, fan_card: { ...card, detail: { score: "1–0" } } })).toBe("1–0");
    expect(scoreText({ ...ticker, payload: { score: [2, 1] } })).toBe("2–1");
  });

  it("has nothing to say for a packet without a score", () => {
    expect(scoreText(approved)).toBeNull();
  });
});

describe("nextStrip (the strip across matches)", () => {
  const goal: Packet = { ...ticker, t_in_ms: 2_530_000, payload: { score: [1, 0] } };
  const after = (p: Packet, ms: number): Packet => ({ ...p, cue_id: `c-${ms}`, t_in_ms: ms });

  it("keeps the last score through packets that carry none", () => {
    const s = nextStrip(nextStrip(null, goal), after(approved, 2_560_000));
    expect(s.score).toBe("1–0");
  });

  it("keeps it for a late packet within the package offset", () => {
    const s = nextStrip(nextStrip(null, goal), after(approved, goal.t_in_ms - 25_000));
    expect(s.score).toBe("1–0");
  });

  it("starts over at nothing for another match", () => {
    const s = nextStrip(nextStrip(null, goal), { ...approved, match_id: "m-2" });
    expect(s.score).toBeUndefined();
  });

  it("starts over for Run again of the same match, which goes back in play time", () => {
    const end = nextStrip(nextStrip(null, goal), after(approved, 2_750_000));
    const rerun = nextStrip(end, after(approved, 2_465_000));
    expect(rerun.score).toBeUndefined();
    expect(nextStrip(rerun, after(goal, 2_530_000)).score).toBe("1–0");
  });
});

describe("the latest shot on the viewer's pitch", () => {
  const shot: Packet = {
    ...approved, cue_id: "c-shot", t_in_ms: 2_480_000,
    payload: { intel: { player: "har-09", shot_path: [[94, 51], [100, 50]], names: { "har-09": "Finn Oakes" } } },
  };

  it("takes only the path the stats engine sent", () => {
    expect(shotOf(shot)).toEqual({ points: [[94, 51], [100, 50]], player: "har-09", name: "Finn Oakes" });
    expect(shotOf(approved)).toBeNull();
    expect(shotOf({ ...shot, payload: { intel: { shot_path: [[94, 51]] } } })).toBeNull();
  });

  it("stays between graphics and goes with the match", () => {
    const kept = nextStrip(nextStrip(null, shot), { ...approved, cue_id: "c-next", t_in_ms: 2_490_000 });
    expect(kept.shot?.points).toEqual([[94, 51], [100, 50]]);
    expect(nextStrip(kept, { ...approved, match_id: "m-2" }).shot).toBeUndefined();
  });
});

describe("withStanding (the score on connect, from GET /state)", () => {
  const standing = { matchId: "m-1", playMs: 2_500_000, home: 1, away: 0 };

  it("gives a refreshed screen the score at once", () => {
    expect(withStanding(null, standing)).toMatchObject({ matchId: "m-1", score: "1–0", latestMs: 2_500_000 });
  });

  it("keeps a packet's own framing for this run", () => {
    const framed = { matchId: "m-1", latestMs: 2_490_000, score: "winning 1–0", color: "#0b3d91" };
    expect(withStanding(framed, standing)).toMatchObject({ score: "winning 1–0", color: "#0b3d91" });
  });

  it("starts over from the count for another match or a rerun", () => {
    const old = { matchId: "m-1", latestMs: 2_750_000, score: "1–0" };
    expect(withStanding(old, { ...standing, playMs: 2_461_000, home: 0 }).score).toBe("0–0");
    expect(withStanding(old, { ...standing, matchId: "m-2", home: 2 }).score).toBe("2–0");
  });
});

describe("viewer settings in the URL", () => {
  it("round-trips, so a refresh brings back the same viewer", () => {
    const s = { persona: "newcomer", access: "deaf", lang: "es", allegiance: "home" } as const;
    expect(settingsFromQuery(`?${queryFor(s)}`)).toEqual(s);
  });

  it("ignores values it does not know", () => {
    expect(settingsFromQuery("?persona=coach&lang=fr&access=deaf")).toEqual({
      persona: undefined, access: "deaf", lang: undefined, allegiance: undefined,
    });
  });
});

describe("kickerFor (the line above a graphic, from data the packet carries)", () => {
  it("says what happened, from the caption card's outcome, in the viewer's language", () => {
    const goal = { ...lead, fan_card: { ...card, detail: { outcome: "goal" } } };
    expect(kickerFor(goal, "en")).toBe("Goal");
    expect(kickerFor(goal, "es")).toBe("Gol");
  });

  it("marks the goal ticker as the score and the scorer's lower third as the stats", () => {
    expect(kickerFor({ ...ticker, payload: { score: [1, 0] } }, "en")).toBe("Score");
    expect(kickerFor({ ...approved, payload: { source: "code" } as Packet["payload"] }, "en")).toBe("Stats");
  });

  it("falls back to a shot, then to Live", () => {
    expect(kickerFor({ ...approved, payload: { intel: { shot_speed_kmh: 88.1 } } }, "en")).toBe("Shot");
    expect(kickerFor(approved, "hi")).toBe("लाइव");
  });
});

describe("isRestart (a new run, seen from the GET /state poll)", () => {
  const was = { matchId: "m-1", playMs: 2_790_000, home: 1, away: 0 };

  it("is a new run when the match goes away while the API loads the next one", () => {
    expect(isRestart(was, null)).toBe(true);
  });

  it("is a new run on another match, or on play time gone back at all", () => {
    expect(isRestart(was, { ...was, matchId: "m-2" })).toBe(true);
    expect(isRestart(was, { ...was, playMs: 2_461_000, home: 0 })).toBe(true);
    expect(isRestart(was, { ...was, playMs: 2_789_000 })).toBe(true); // a short window run again
  });

  it("is not the same run moving on, nor a first look", () => {
    expect(isRestart(was, { ...was, playMs: 2_792_000 })).toBe(false);
    expect(isRestart(was, was)).toBe(false); // the clock between events
    expect(isRestart(null, was)).toBe(false);
    expect(isRestart(null, null)).toBe(false);
  });
});

describe("cueWord (the strike cue, #54)", () => {
  it("says the cue in the viewer's language", () => {
    expect(cueWord("chance", "en")).toBe("Shot");
    expect(cueWord("goal", "hi")).toBe("गोल");
    expect(cueWord("crowd_roar", "es")).toBe("Rugido de la grada");
  });

  it("says Play, in the viewer's language, for a kind it does not know", () => {
    expect(cueWord("new_kind", "es")).toBe("Juego");
  });
});

describe("the pickers' help", () => {
  it("explains every persona and every access choice", () => {
    for (const p of ["newcomer", "fan", "analyst"] as const) expect(PERSONA_HELP[p].length).toBeGreaterThan(20);
    for (const a of ["none", "deaf"] as const) expect(ACCESS_HELP[a].length).toBeGreaterThan(10);
  });
});

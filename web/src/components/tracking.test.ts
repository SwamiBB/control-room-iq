import { describe, expect, it } from "vitest";
import { H, W } from "./pitchGeometry";
import { asFrame, homeOf, nextTrail, shirtOf, shotMirror, teamOf, toPitch, TRAIL_MS, type TrackingFrame } from "./tracking";

const frame = (play_ms: number, players: TrackingFrame["players"] = { "har-09": [40, 50], "nfu-01": [96, 50] }) =>
  ({ play_ms, period: 1, ball: [50, 50, 0], players }) as TrackingFrame;

describe("asFrame", () => {
  it("takes a frame as the API sends it", () => {
    const f = asFrame({ frame: 4, play_ms: 1000, period: 1, t_ms: 1000, ball: [50, 50, 1.5], players: { "har-09": [40, 50] } });
    expect(f).toEqual({ play_ms: 1000, period: 1, ball: [50, 50, 1.5], players: { "har-09": [40, 50] } });
  });

  it("refuses a frame without a time or a ball, and drops a malformed player", () => {
    expect(asFrame(null)).toBeNull();
    expect(asFrame({ period: 1, ball: [50, 50, 0], players: {} })).toBeNull();
    expect(asFrame({ play_ms: 0, period: 1, ball: [50, 50], players: {} })).toBeNull();
    expect(asFrame({ play_ms: 0, period: 1, ball: [50, 50, 0], players: { a: [1, 2], b: ["x", 2] } })?.players)
      .toEqual({ a: [1, 2] });
  });
});

describe("players", () => {
  it("reads the team and shirt number from the id", () => {
    expect(teamOf("har-09")).toBe("har");
    expect(shirtOf("har-09")).toBe(9);
    expect(shirtOf("ref")).toBeNull();
  });

  it("knows the home side from the score bug, or else from the order the file lists them", () => {
    expect(homeOf(frame(0), "nfu")).toBe("nfu");
    expect(homeOf(frame(0))).toBe("har");
  });

  it("puts tracking's 0-100 on the pitch's metres", () => {
    expect(toPitch(0, 0)).toEqual({ cx: 0, cy: 0 });
    expect(toPitch(100, 100)).toEqual({ cx: W, cy: H });
  });
});

describe("shotMirror (a shot relative to its team, on the tracking pitch)", () => {
  it("leaves a home shot in the first half as it is", () => {
    expect(shotMirror("har-09", "har", 1)).toBe(false);
  });

  it("turns an away shot, and any shot after the ends change", () => {
    expect(shotMirror("nfu-09", "har", 1)).toBe(true);
    expect(shotMirror("har-09", "har", 2)).toBe(true);
    expect(shotMirror("nfu-09", "har", 2)).toBe(false);
  });

  it("leaves a shot it cannot place as it is", () => {
    expect(shotMirror(null, "har", 1)).toBe(false);
    expect(shotMirror("nfu-09", undefined, 1)).toBe(false);
  });
});

describe("nextTrail", () => {
  it("keeps the last two seconds of play", () => {
    let trail: TrackingFrame[] = [];
    for (let t = 0; t <= 4000; t += 250) trail = nextTrail(trail, frame(t));
    expect(trail[0].play_ms).toBe(4000 - TRAIL_MS);
    expect(trail[trail.length - 1].play_ms).toBe(4000);
  });

  it("starts over when play goes back: a new run", () => {
    expect(nextTrail([frame(5000), frame(5250)], frame(1000))).toEqual([frame(1000)]);
  });
});

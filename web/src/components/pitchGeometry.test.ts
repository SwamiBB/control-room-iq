import { describe, expect, it } from "vitest";
import { asPath, pathD } from "./pitchGeometry";
import { latestShotPath } from "./PitchView";

describe("pathD (the ball's path, through the given points only)", () => {
  it("draws a two-point shot from where it was struck to where it finished", () => {
    expect(pathD([[94, 51], [100, 50]], false)).toBe("M 98.70 34.68 L 105.00 34.00");
  });

  it("takes a longer trail in order, unchanged, so a move can replace the two points", () => {
    const d = pathD([[29, 37], [39, 39.6], [89, 47], [100, 50]], false);
    expect(d?.split(" L ")).toHaveLength(4);
    expect(d?.startsWith("M 30.45 25.16")).toBe(true);
  });

  it("rotates the away side's path with its markers", () => {
    expect(pathD([[94, 51], [100, 50]], true)).toBe("M 6.30 33.32 L 0.00 34.00");
  });

  it("draws nothing from fewer than two points: one point has no direction", () => {
    expect(pathD([[94, 51]], false)).toBeNull();
    expect(pathD([], false)).toBeNull();
    expect(pathD(null, false)).toBeNull();
  });
});

describe("asPath (what the stats engine sent, checked)", () => {
  it("accepts ordered [x, y] pairs", () => {
    expect(asPath([[94, 51], [100, 50]])).toEqual([[94, 51], [100, 50]]);
  });

  it("refuses anything else rather than guessing", () => {
    expect(asPath(undefined)).toBeNull();
    expect(asPath([[94, 51]])).toBeNull();
    expect(asPath([[94, 51], [100]])).toBeNull();
    expect(asPath([[94, 51], [100, null]])).toBeNull();
    expect(asPath("94,51;100,50")).toBeNull();
  });
});

describe("latestShotPath (the operator's newest moment with a shot)", () => {
  const name = (id?: string | null) => (id === "har-09" ? "Finn Oakes" : id ?? "");
  const strike = { moment: { player: "har-09", event_ids: ["e-taken"], metrics: { shot_path: null } } };
  const result = {
    moment: { team: "har", player: "har-09", event_ids: ["e-shot"], metrics: { shot_path: [[94, 51], [100, 50]] } },
  };
  const older = { moment: { team: "nfu", player: "nfu-09", event_ids: ["e-old"] }, intel: { shot_path: [[80, 40], [100, 47]] } };

  it("takes the newest moment that has one, labelled as the shot", () => {
    expect(latestShotPath([strike, result, older], name)).toEqual({
      id: "e-shot", team: "har", points: [[94, 51], [100, 50]], label: "Shot by Finn Oakes",
    });
  });

  it("falls back to the intel block, and to nothing", () => {
    expect(latestShotPath([older], name)?.points).toEqual([[80, 40], [100, 47]]);
    expect(latestShotPath([strike], name)).toBeNull();
    expect(latestShotPath([], name)).toBeNull();
  });
});

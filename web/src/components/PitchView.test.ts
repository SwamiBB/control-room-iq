import { describe, expect, it } from "vitest";
import { place, radius } from "./PitchView";

describe("place", () => {
  it("mirrors an away-team shot through the centre spot", () => {
    const { cx, cy } = place(80, 30, true);
    expect(cx).toBeCloseTo(21); // (100 - 80) % of 105 m
    expect(cy).toBeCloseTo(47.6); // (100 - 30) % of 68 m
  });

  it("leaves a home-team shot where it is", () => {
    const { cx, cy } = place(80, 30, false);
    expect(cx).toBeCloseTo(84);
    expect(cy).toBeCloseTo(20.4);
  });
});

describe("radius", () => {
  it("grows with xG", () => {
    expect(radius(0.1)).toBeLessThan(radius(0.5));
    expect(radius(0.5)).toBeLessThan(radius(0.9));
  });

  it("is clamped at xG 0 and xG 1", () => {
    expect(radius(-0.5)).toBe(radius(0));
    expect(radius(1.7)).toBe(radius(1));
  });
});

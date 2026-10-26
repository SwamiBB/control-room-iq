import { describe, expect, it } from "vitest";
import { stableOrder } from "./runningOrder";

const s = (key: string, weight: number) => ({ key, weight });

describe("stableOrder (the running order holds still)", () => {
  it("places an arrival by priority among the cards already there", () => {
    expect(stableOrder(["a", "b"], [s("a", 1), s("b", 3), s("goal", 2)], false).order).toEqual(["a", "goal", "b"]);
  });

  it("never moves a card once placed, whatever its weight does after", () => {
    expect(stableOrder(["a", "b"], [s("a", 9), s("b", 1)], false).order).toEqual(["a", "b"]);
  });

  it("drops a decided card and closes the gap without reordering the rest", () => {
    expect(stableOrder(["a", "b", "c"], [s("a", 1), s("c", 1)], false).order).toEqual(["a", "c"]);
  });

  it("puts an arrival at the bottom while the pointer is on the list: on screen, nothing above it moves", () => {
    const held = stableOrder(["a", "b"], [s("a", 3), s("b", 3), s("goal", 1)], true);
    expect(held).toEqual({ order: ["a", "b", "goal"], pending: ["goal"] });
  });

  it("moves pending cards once into their place when the list is free", () => {
    const cards = [s("a", 3), s("b", 3), s("goal", 1)];
    const held = stableOrder(["a", "b"], cards, true);
    expect(stableOrder(held.order, cards, false, held.pending)).toEqual({ order: ["goal", "a", "b"], pending: [] });
  });

  it("keeps a pending card pending across updates while still frozen, and forgets it once decided", () => {
    const held = stableOrder(["a"], [s("a", 3), s("goal", 1)], true);
    expect(stableOrder(held.order, [s("a", 3), s("goal", 1)], true, held.pending).pending).toEqual(["goal"]);
    expect(stableOrder(held.order, [s("a", 3)], true, held.pending)).toEqual({ order: ["a"], pending: [] });
  });

  it("starts from priority on a fresh desk", () => {
    expect(stableOrder([], [s("x", 3), s("y", 1), s("z", 2)], false).order).toEqual(["y", "z", "x"]);
  });
});

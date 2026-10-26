import { describe, expect, it } from "vitest";
import { BUG_RECT, LAYERS, LAYER_RECTS, canShareFrame, layerOf, onScreen, overlaps } from "./layout";

const h = (cue: string, layer: string) => ({ cue, packet: { layer } });

describe("layer positions", () => {
  it("never overlaps two layers that can be on screen together", () => {
    for (const a of LAYERS) {
      for (const b of LAYERS) {
        if (canShareFrame(a, b)) expect(overlaps(LAYER_RECTS[a], LAYER_RECTS[b]), `${a} and ${b}`).toBe(false);
      }
    }
  });

  it("never puts a layer over the score bug, which is always on screen", () => {
    for (const l of LAYERS) expect(overlaps(LAYER_RECTS[l], BUG_RECT), l).toBe(false);
  });

  it("keeps every region inside the frame", () => {
    for (const r of Object.values(LAYER_RECTS)) {
      expect(r.top >= 0 && r.left >= 0 && r.top + r.height <= 100 && r.left + r.width <= 100).toBe(true);
    }
  });

  it("follows the convention: lower third bottom left, ticker full width at the bottom, full screen centred", () => {
    const { lower_third: lt, ticker: tk, full_screen: fs } = LAYER_RECTS;
    expect(lt.left).toBeLessThan(10);
    expect(lt.top + lt.height).toBeLessThanOrEqual(tk.top);
    expect([tk.left, tk.width, tk.top + tk.height]).toEqual([0, 100, 100]);
    expect(fs.left + fs.width / 2).toBe(50);
  });

  it("treats an unknown layer as a lower third rather than dropping it", () => {
    expect(layerOf("something_new")).toBe("lower_third");
  });
});

describe("onScreen", () => {
  it("shows the goal routine's three graphics together", () => {
    const live = [h("ticker", "ticker"), h("stats", "lower_third"), h("lead", "full_screen")];
    expect(onScreen(live).map((x) => x.cue).sort()).toEqual(["lead", "stats", "ticker"]);
  });

  it("keeps one graphic per layer, the newest", () => {
    expect(onScreen([h("new", "lower_third"), h("old", "lower_third")]).map((x) => x.cue)).toEqual(["new"]);
  });

  it("holds side panels under a full-screen graphic, and brings them back after", () => {
    const panel = h("panel", "stat_panel");
    expect(onScreen([h("lead", "full_screen"), panel]).map((x) => x.cue)).toEqual(["lead"]);
    expect(onScreen([panel]).map((x) => x.cue)).toEqual(["panel"]);
  });
});

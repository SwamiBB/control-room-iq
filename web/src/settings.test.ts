import { describe, expect, it } from "vitest";
import { DEFAULT_SETTINGS, SETTINGS_KEY, loadSettings, newArrivals, saveSettings, shortcutFor } from "./settings";

const memory = (init: Record<string, string> = {}) => {
  const data = { ...init };
  return { data, getItem: (k: string) => data[k] ?? null, setItem: (k: string, v: string) => { data[k] = v; } };
};

describe("operator settings", () => {
  it("defaults to the console as it was: reasoning and preview shown, no shortcuts, no alert", () => {
    expect(loadSettings(memory())).toEqual({ reasoning: true, preview: true, shortcuts: false, alert: false });
  });

  it("round-trips through the browser's storage", () => {
    const store = memory();
    saveSettings(store, { ...DEFAULT_SETTINGS, shortcuts: true, preview: false });
    expect(loadSettings(store)).toEqual({ reasoning: true, preview: false, shortcuts: true, alert: false });
  });

  it("falls back field by field on a bad or partial value", () => {
    expect(loadSettings(memory({ [SETTINGS_KEY]: "not json" }))).toEqual(DEFAULT_SETTINGS);
    expect(loadSettings(memory({ [SETTINGS_KEY]: '{"alert":true,"preview":"no","extra":1}' })))
      .toEqual({ ...DEFAULT_SETTINGS, alert: true });
  });

  it("survives storage that throws", () => {
    const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
    expect(loadSettings(broken)).toEqual(DEFAULT_SETTINGS);
    expect(() => saveSettings(broken, DEFAULT_SETTINGS)).not.toThrow();
  });

  it("has exactly four switches, and none hides template-built cards", () => {
    expect(Object.keys(DEFAULT_SETTINGS).sort()).toEqual(["alert", "preview", "reasoning", "shortcuts"]);
  });
});

describe("shortcutFor", () => {
  it("maps F, H and D to fire, hold and drop, either case", () => {
    expect(shortcutFor({ key: "f" })).toBe("approve");
    expect(shortcutFor({ key: "H" })).toBe("hold");
    expect(shortcutFor({ key: "d" })).toBe("reject");
    expect(shortcutFor({ key: "x" })).toBeNull();
  });

  it("ignores typing in a field, modifiers and key repeat", () => {
    expect(shortcutFor({ key: "f", target: { tagName: "input" } })).toBeNull();
    expect(shortcutFor({ key: "f", target: { tagName: "SELECT" } })).toBeNull();
    expect(shortcutFor({ key: "d", target: { tagName: "DIV", isContentEditable: true } })).toBeNull();
    expect(shortcutFor({ key: "f", ctrlKey: true })).toBeNull();
    expect(shortcutFor({ key: "f", metaKey: true })).toBeNull();
    expect(shortcutFor({ key: "f", repeat: true })).toBeNull();
  });
});

describe("newArrivals", () => {
  it("counts a waiting graphic once, not again when the API re-sends it on reconnect", () => {
    const seen = new Set<string>();
    expect(newArrivals(seen, [{ proposal_id: "p1", status: "proposed" }])).toEqual(["p1"]);
    expect(newArrivals(seen, [{ proposal_id: "p1", status: "proposed" }])).toEqual([]);
    expect(newArrivals(seen, [{ proposal_id: "p1", status: "held" }])).toEqual([]);
  });

  it("does not count a card first seen already decided", () => {
    expect(newArrivals(new Set(), [{ proposal_id: "p2", status: "aired" }])).toEqual([]);
  });
});

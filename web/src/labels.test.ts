import { describe, expect, it } from "vitest";
import {
  ACCESS_HELP_TEXT, ACCESS_NAMES, PERSONA_HELP_TEXT, PERSONA_NAMES, SIDE_NAMES, VIEWER_UI, chanceText, isOutcome,
  keepTogether, outcomeText, supporterText, zoneText, type Lang,
} from "./labels";

const ENGLISH = "about 1 in 3 chances like this go in";

describe("chanceText", () => {
  it("gives 1 in 3 for xG 0.34 in Spanish", () => {
    expect(chanceText(0.34, ENGLISH, "es")).toBe("alrededor de 1 de cada 3 ocasiones así acaban en gol");
  });

  it("gives 1 in 3 for xG 0.34 in Hindi", () => {
    expect(chanceText(0.34, ENGLISH, "hi")).toBe("ऐसे लगभग 3 में से 1 मौका गोल बनता है");
  });

  it("gives 6 in 10 for xG 0.6 in Spanish (the >= 0.5 branch)", () => {
    expect(chanceText(0.6, ENGLISH, "es")).toBe("alrededor de 6 de cada 10 ocasiones así acaban en gol");
  });

  // The brief asked for "floors the denominator at 2, not 20" at xG 0.05. The code gives 20 there:
  // round(1 / 0.05) = 20, and Math.max(2, …) only bites when round(1/xG) < 2, which needs xG > 0.67,
  // and those take the >= 0.5 branch. This pins today's behaviour; see the report.
  it("gives 1 in 20 for xG 0.05 (the minimum of 2 never applies below xG 0.5)", () => {
    expect(chanceText(0.05, ENGLISH, "es")).toBe("alrededor de 1 de cada 20 ocasiones así acaban en gol");
    expect(chanceText(0.49, ENGLISH, "es")).toBe("alrededor de 1 de cada 2 ocasiones así acaban en gol");
  });

  it("returns the English wording unchanged in English, ignoring xG", () => {
    expect(chanceText(0.9, ENGLISH, "en")).toBe(ENGLISH);
    expect(chanceText(null, ENGLISH, "en")).toBe(ENGLISH);
  });

  it("returns null for a null or zero xG outside English", () => {
    expect(chanceText(null, ENGLISH, "es")).toBeNull();
    expect(chanceText(0, ENGLISH, "es")).toBeNull();
  });
});

describe("zoneText", () => {
  it("translates both halves of the zone into Spanish", () => {
    expect(zoneText("edge of the box, left", "es")).toBe("borde del área, izquierda");
  });

  it("translates both halves of the zone into Hindi", () => {
    expect(zoneText("edge of the box, left", "hi")).toBe("बॉक्स के किनारे, बाएँ");
  });

  it("passes an unknown area through unchanged rather than dropping it", () => {
    expect(zoneText("halfway line, left", "es")).toBe("halfway line, izquierda");
  });
});

describe("outcomeText", () => {
  const cases: Array<[string, Lang, string]> = [
    ["goal", "en", "Goal"], ["goal", "es", "Gol"], ["goal", "hi", "गोल"],
    ["saved", "en", "Saved"], ["saved", "es", "Atajado"], ["saved", "hi", "बचाया गया"],
    ["off_target", "en", "Off target"], ["off_target", "es", "Fuera"], ["off_target", "hi", "निशाने से बाहर"],
    ["blocked", "en", "Blocked"], ["blocked", "es", "Bloqueado"], ["blocked", "hi", "ब्लॉक किया गया"],
  ];
  it.each(cases)("%s in %s is %s", (code, lang, want) => {
    expect(outcomeText(code, lang)).toBe(want);
  });
});

describe("supporterText (the score from the viewer's side, under the bug)", () => {
  it("frames the live score for each side, in each language, as perspective.py does", () => {
    expect(supporterText(1, 0, "home", "en")).toBe("1–0 up");
    expect(supporterText(1, 0, "away", "en")).toBe("0–1 down");
    expect(supporterText(1, 1, "away", "es")).toBe("empatando 1–1");
    expect(supporterText(2, 1, "home", "es")).toBe("ganando 2–1");
    expect(supporterText(0, 2, "home", "hi")).toBe("0–2 से पीछे");
  });

  it("says nothing to a neutral viewer", () => {
    expect(supporterText(1, 0, "neutral", "en")).toBeNull();
  });
});

describe("isOutcome", () => {
  it("knows the stats engine's codes and nothing else", () => {
    expect(isOutcome("goal")).toBe(true);
    expect(isOutcome("constructor")).toBe(false);
    expect(isOutcome(undefined)).toBe(false);
  });
});

describe("keepTogether (where a drawn line may break)", () => {
  const NBSP = " ", WJ = "⁠";

  it("keeps a number with its unit", () => {
    expect(keepTogether("a 1-0 lead at 88.1 km/h.")).toBe(`a${NBSP}1-${WJ}0 lead at 88.1${NBSP}km/h.`);
    expect(keepTogether("Finn Oakes 5.42 km · 6 sprints")).toBe(`Finn Oakes 5.42${NBSP}km · 6 sprints`);
  });

  it("keeps the score in one piece and with the word before it", () => {
    expect(keepTogether("गोल किया! स्कोर 1–0")).toBe(`गोल किया! स्कोर${NBSP}1–${WJ}0`);
    expect(keepTogether("Marcador: 2–1")).toBe(`Marcador:${NBSP}2–${WJ}1`);
  });

  it("changes no words: only spaces and an invisible joiner", () => {
    const line = "GOAL — Finn Oakes fires Harbor City into a 1-0 lead over Northfield United at 88.1 km/h.";
    expect(keepTogether(line).replaceAll(NBSP, " ").replaceAll(WJ, "")).toBe(line);
    expect(keepTogether("No numbers here")).toBe("No numbers here");
    expect(keepTogether("a 4-3-3 shape")).toBe(`a${NBSP}4-${WJ}3-${WJ}3 shape`);
  });
});

describe("the viewer page's own words", () => {
  const tables = { VIEWER_UI, PERSONA_NAMES, ACCESS_NAMES, SIDE_NAMES, PERSONA_HELP_TEXT, ACCESS_HELP_TEXT };

  it("has every entry in all three languages", () => {
    for (const [table, rows] of Object.entries(tables))
      for (const [key, row] of Object.entries(rows as Record<string, Record<Lang, string>>))
        for (const lang of ["en", "es", "hi"] as const) expect(row[lang]?.trim(), `${table}.${key}.${lang}`).toBeTruthy();
  });

  it("puts no English sentence on a Hindi page", () => {
    for (const [key, row] of Object.entries(VIEWER_UI)) expect(row.hi, key).not.toBe(row.en);
  });
});

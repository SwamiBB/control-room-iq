import { afterEach, describe, expect, it, vi } from "vitest";
import { decisionLabel, fetchPreview, layerName, modelLabel, viewLabel } from "./api";

describe("fetchPreview", () => {
  afterEach(() => vi.unstubAllGlobals());

  // GET /proposals/{id}/preview as preview.py's Preview model serialises it.
  const body = {
    proposal_id: "p-7",
    override_line: null,
    items: [
      {
        view: { key: "fan.none.es.home", persona: "fan", access: "none", lang: "es", allegiance: "home" },
        source: "variant",
        text: "¡Gran ocasión para Oli Stone!",
        lang_shown: "es",
        failures: [],
        perspective: { side: "home", team: "Rivertown", score: [1, 0] },
      },
      {
        view: { key: "newcomer.deaf.hi.neutral", persona: "newcomer", access: "deaf", lang: "hi", allegiance: "neutral" },
        source: "base",
        text: "Big chance for Oli Stone.",
        lang_shown: "en",
        failures: ["numbers_mismatch"],
        perspective: null,
      },
    ],
  };

  it("reads items, one line per viewer group, with the group as an object", async () => {
    const fetch = vi.fn(async (_url: string) => ({ ok: true, json: async () => body }));
    vi.stubGlobal("fetch", fetch);

    const lines = await fetchPreview("p-7", ["fan.none.es.home", "newcomer.deaf.hi.neutral"]);

    expect(lines).toHaveLength(2);
    expect(lines.map((l) => l.view.key)).toEqual(["fan.none.es.home", "newcomer.deaf.hi.neutral"]);
    expect(lines[1].failures).toEqual(["numbers_mismatch"]);
    expect(String(fetch.mock.calls[0][0])).toContain("view=fan.none.es.home&view=newcomer.deaf.hi.neutral");
  });

  it("labels each line by its group's key", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => body })));
    const lines = await fetchPreview("p-7", ["fan.none.es.home"]);
    expect(lines.map((l) => viewLabel(l.view.key))).toEqual(["es fan", "hi newcomer · deaf"]);
  });
});

describe("layerName", () => {
  it("says lower_third as 'Lower third', not 'Lower Third'", () => {
    expect(layerName("lower_third")).toBe("Lower third");
  });
});

describe("modelLabel", () => {
  it("returns Template when the fallback wrote the line", () => {
    expect(modelLabel({ fallback: true, meta: { routing: "router-quality", model_served: "gpt-4.1" } })).toBe("Template");
  });

  it("returns Template when routing is template", () => {
    expect(modelLabel({ fallback: false, meta: { routing: "template", model_served: "gpt-4.1" } })).toBe("Template");
  });

  it("returns the served model otherwise", () => {
    expect(modelLabel({ fallback: false, meta: { routing: "router-quality", model_served: "gpt-4.1" } })).toBe("gpt-4.1");
  });
});

describe("decisionLabel", () => {
  it("says Held by the timer for the sla-timer actor, whatever the action", () => {
    expect(decisionLabel("held", "sla-timer")).toBe("Held by the timer");
    expect(decisionLabel("approved", "sla-timer")).toBe("Held by the timer");
  });

  it("says Expired for the expiry-rule actor", () => {
    expect(decisionLabel("held", "expiry-rule")).toBe("Expired");
  });

  it("says Overridden for an override", () => {
    expect(decisionLabel("overridden", "operator")).toBe("Overridden");
  });
});

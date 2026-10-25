import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DEMO_WINDOW, decide, decisionLabel, errorMessage, fetchPreview, layerName, modelLabel, startReplay, viewLabel,
} from "./api";

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

describe("errorMessage", () => {
  afterEach(() => vi.unstubAllGlobals());

  const answer = (status: number, body: string) =>
    vi.stubGlobal("fetch", vi.fn(async () => new Response(body, { status })));

  const failure = async () => {
    try {
      await decide("p-7", "approve");
    } catch (err) {
      return err;
    }
    throw new Error("decide did not fail");
  };

  it("turns a 409 into a sentence instead of raw JSON", async () => {
    answer(409, JSON.stringify({ detail: "proposal already approved" }));
    const text = errorMessage(await failure(), "fire the graphic");
    expect(text).toBe("Couldn't fire the graphic: proposal already approved. Nothing was changed.");
    expect(text).not.toContain("{");
  });

  it("joins a validation error's messages", async () => {
    answer(422, JSON.stringify({ detail: [{ loc: ["body", "override_line"], msg: "String should have at most 280 characters" }] }));
    expect(errorMessage(await failure(), "fire the override"))
      .toBe("Couldn't fire the override: String should have at most 280 characters (422).");
  });
});

describe("startReplay", () => {
  afterEach(() => vi.unstubAllGlobals());

  const sent = async (...args: Parameters<typeof startReplay>) => {
    const fetch = vi.fn(async (_url: string, _init: RequestInit) => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    await startReplay(...args);
    return JSON.parse(String(fetch.mock.calls[0][1].body));
  };

  it("sends the picked speed for the dead air, over the demo window", async () => {
    const body = await sent("window", 50);
    expect(body.speed).toBe(50);
    expect(body.from_play_ms).toBe(DEMO_WINDOW.from_play_ms);
  });

  it("defaults to 20x and leaves decision_speed to the API, so decisions stay at real time", async () => {
    const body = await sent();
    expect(body.speed).toBe(20);
    expect(body).not.toHaveProperty("decision_speed");
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DEMO_WINDOW, decide, decisionLabel, errorMessage, fetchMetrics, fetchPreview, isTemplateFallback, layerName, modelLabel, startReplay, viewLabel,
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

  it("says a 500 is the API's own failure and where to look, not a bare status", async () => {
    answer(500, "Internal Server Error");
    const text = errorMessage(await failure(), "fire the graphic");
    expect(text).toBe("Couldn't fire the graphic: the API failed while handling it (500). Its terminal has the error; "
      + "try again, and restart the API if it keeps happening.");
  });

  it("says the API is not answering, and where, when the request never got an answer", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const err = await fetchMetrics().catch((e) => e);
    expect(errorMessage(err, "load the gallery metrics")).toBe(
      "Couldn't load the gallery metrics: the API at http://localhost:8000 isn't answering. "
      + "Check that it is running, then try again.");
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

describe("code-built items are not template fallbacks", () => {
  // As the API sends a goal routine's items: the follow-ups have no meta, so routing is the default "template".
  const noMeta = { routing: "template", model_served: null, latency_ms: null };
  const lead = { fallback: false, meta: { routing: "balanced", model_served: "gpt-5.6-terra" }, package_seq: 0, payload: {} };
  const stats = { fallback: false, meta: noMeta, package_seq: 1, payload: { source: "code", player_id: "har-06" } };
  const ticker = { fallback: false, meta: noMeta, package_seq: 2, payload: { source: "code", score: [1, 0] } };
  const fallbackLead = { fallback: true, meta: noMeta, package_seq: 0, payload: {} };

  it("counts none of a model-written routine as a fallback", () => {
    expect([lead, stats, ticker].filter(isTemplateFallback)).toHaveLength(0);
  });

  it("still counts a lead the template wrote", () => {
    expect([fallbackLead, stats, ticker].filter(isTemplateFallback)).toEqual([fallbackLead]);
  });

  it("labels the follow-ups Official stats, not Template", () => {
    expect([lead, stats, ticker, fallbackLead].map(modelLabel)).toEqual(["gpt-5.6-terra", "Official stats", "Official stats", "Template"]);
  });
});

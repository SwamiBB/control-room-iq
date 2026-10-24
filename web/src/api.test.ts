import { describe, expect, it } from "vitest";
import { decisionLabel, layerName, modelLabel } from "./api";

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

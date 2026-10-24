import { describe, expect, it } from "vitest";
import { isApproved, type Packet } from "./Viewer";

// The renderer's half of the gate: no approval fields, no drawing.
const approved: Packet = {
  cue_id: "c-1",
  match_id: "m-1",
  layer: "lower_third",
  line: "Big chance for Oli Stone.",
  lang: "en",
  access: "none",
  profile: "fan",
  allegiance: "neutral",
  verified: true,
  fallback: false,
  min_hold_ms: 4000,
  replaces: [],
  approval_id: "a-1",
  approved_by: "operator",
  approved_at: "2026-10-24T12:00:00Z",
};

describe("isApproved (the gate)", () => {
  it("accepts a packet with approval_id, approved_by and approved_at", () => {
    expect(isApproved(approved)).toBe(true);
  });

  it("refuses a packet missing approval_id", () => {
    const { approval_id: _, ...p } = approved;
    expect(isApproved(p)).toBe(false);
  });

  it("refuses a packet missing approved_by", () => {
    const { approved_by: _, ...p } = approved;
    expect(isApproved(p)).toBe(false);
  });

  it("refuses a packet missing approved_at", () => {
    const { approved_at: _, ...p } = approved;
    expect(isApproved(p)).toBe(false);
  });

  it("refuses a packet with an empty-string approval_id", () => {
    expect(isApproved({ ...approved, approval_id: "" })).toBe(false);
  });
});

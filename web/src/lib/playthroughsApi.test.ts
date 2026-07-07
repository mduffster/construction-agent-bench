import { describe, expect, it } from "vitest";

import { validateNodeIds, validatePlaythrough } from "../../api/playthroughs";

const validBody = {
  role: "steel_supplier",
  decisions: {
    S01_A1_SUPPLIER_APPLICATION: "balanced",
    S01_B1_SUPPLIER_COMMERCIAL_POSITION: "conservative",
    S01_C1_SUPPLIER_SHIP_DECISION: "self_protective",
  },
  projectSuccess: true,
  privateSuccess: false,
  costUsd: 95_850_000,
  completionWeek: 41,
};

describe("validatePlaythrough", () => {
  it("accepts a well-formed playthrough and rounds numerics", () => {
    const record = validatePlaythrough({ ...validBody, costUsd: 95_850_000.6 });
    expect(record).not.toBeNull();
    expect(record?.costUsd).toBe(95_850_001);
    expect(record?.decisions.S01_A1_SUPPLIER_APPLICATION).toBe("balanced");
  });

  it("rejects unknown roles and system roles", () => {
    expect(validatePlaythrough({ ...validBody, role: "lender" })).toBeNull();
    expect(validatePlaythrough({ ...validBody, role: "hacker" })).toBeNull();
  });

  it("rejects unknown choice ids and malformed node ids", () => {
    expect(
      validatePlaythrough({
        ...validBody,
        decisions: { S01_A1_SUPPLIER_APPLICATION: "reckless" },
      })
    ).toBeNull();
    expect(
      validatePlaythrough({
        ...validBody,
        decisions: { "s01:injection": "balanced" },
      })
    ).toBeNull();
  });

  it("rejects empty, oversized, and out-of-range payloads", () => {
    expect(validatePlaythrough({ ...validBody, decisions: {} })).toBeNull();
    const oversized = Object.fromEntries(
      Array.from({ length: 7 }, (_, index) => [`S01_NODE_${index}`, "balanced"])
    );
    expect(validatePlaythrough({ ...validBody, decisions: oversized })).toBeNull();
    expect(validatePlaythrough({ ...validBody, costUsd: -5 })).toBeNull();
    expect(validatePlaythrough({ ...validBody, completionWeek: 4000 })).toBeNull();
    expect(validatePlaythrough({ ...validBody, projectSuccess: "yes" })).toBeNull();
    expect(validatePlaythrough(null)).toBeNull();
  });
});

describe("validateNodeIds", () => {
  it("accepts a comma-separated list of known-shaped node ids", () => {
    expect(validateNodeIds("S01_A1_SUPPLIER_APPLICATION,S01_C1_SUPPLIER_SHIP_DECISION")).toEqual([
      "S01_A1_SUPPLIER_APPLICATION",
      "S01_C1_SUPPLIER_SHIP_DECISION",
    ]);
  });

  it("rejects empty, malformed, and oversized lists", () => {
    expect(validateNodeIds(undefined)).toBeNull();
    expect(validateNodeIds("")).toBeNull();
    expect(validateNodeIds("DROP TABLE")).toBeNull();
    expect(
      validateNodeIds(
        Array.from({ length: 7 }, (_, index) => `S01_NODE_${index}`).join(",")
      )
    ).toBeNull();
  });
});

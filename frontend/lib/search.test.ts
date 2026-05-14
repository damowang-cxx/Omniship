import { describe, expect, it } from "vitest";
import { filterAirWaybillsByNumber, normalizeWaybillNumber } from "./search";

describe("waybill number search", () => {
  const items = [
    { number: "784-84063276", status: "Released" },
    { number: "123-456", status: "Received" }
  ];

  it("normalizes hyphenated numbers", () => {
    expect(normalizeWaybillNumber("784-84063276")).toBe("78484063276");
  });

  it("matches number with or without hyphen", () => {
    expect(filterAirWaybillsByNumber(items, "784-84063276")).toHaveLength(1);
    expect(filterAirWaybillsByNumber(items, "78484063276")).toHaveLength(1);
  });
});


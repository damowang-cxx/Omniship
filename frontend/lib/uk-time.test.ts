import { describe, expect, it } from "vitest";
import { formatUkDateTime, fromUkDateTimeLocalValue, toUkDateTimeLocalValue } from "./uk-time";

describe("UK operational times", () => {
  it("shows winter AJ timestamps on the GMT clock", () => {
    expect(formatUkDateTime("2026-11-15T12:27:00+00:00")).toContain("12:27:00 GMT");
    expect(toUkDateTimeLocalValue("2026-11-15T12:27:00Z")).toBe("2026-11-15T12:27");
    expect(fromUkDateTimeLocalValue("2026-11-15T12:27")).toBe("2026-11-15T12:27:00.000Z");
  });

  it("shows summer AJ timestamps on the BST clock", () => {
    expect(formatUkDateTime("2026-07-15T12:27:00+01:00")).toContain("12:27:00 BST");
    expect(toUkDateTimeLocalValue("2026-07-15T11:27:00Z")).toBe("2026-07-15T12:27");
    expect(fromUkDateTimeLocalValue("2026-07-15T12:27")).toBe("2026-07-15T11:27:00.000Z");
  });

  it("rejects a nonexistent spring hour and resolves the repeated autumn hour consistently", () => {
    expect(() => fromUkDateTimeLocalValue("2026-03-29T01:30")).toThrow();
    expect(fromUkDateTimeLocalValue("2026-10-25T01:30")).toBe("2026-10-25T00:30:00.000Z");
  });
});

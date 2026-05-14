import { describe, expect, it } from "vitest";
import { getNextSortState, sortAirWaybills } from "./sort";

describe("air waybill sorting", () => {
  const items = [
    {
      number: "784-84063276",
      status: "part_out",
      weightKgRaw: "1021",
      receivedRaw: "68 / 68",
      parcelsRaw: "68"
    },
    {
      number: "176-28780625",
      status: "inbound",
      weightKgRaw: "1027",
      receivedRaw: "77 / 77",
      parcelsRaw: "77"
    },
    {
      number: "176-28772111",
      status: "noa_received",
      weightKgRaw: "1011",
      receivedRaw: "0 / 82",
      parcelsRaw: "0"
    }
  ];

  it("keeps source order by default", () => {
    expect(sortAirWaybills(items, null).map((item) => item.number)).toEqual([
      "784-84063276",
      "176-28780625",
      "176-28772111"
    ]);
  });

  it("sorts selected numeric columns ascending and descending", () => {
    expect(
      sortAirWaybills(items, { key: "weightKgRaw", direction: "asc" }).map(
        (item) => item.weightKgRaw
      )
    ).toEqual(["1011", "1021", "1027"]);

    expect(
      sortAirWaybills(items, { key: "parcelsRaw", direction: "desc" }).map(
        (item) => item.parcelsRaw
      )
    ).toEqual(["77", "68", "0"]);
  });

  it("cycles sort state through asc, desc, default", () => {
    const asc = getNextSortState(null, "number");
    expect(asc).toEqual({ key: "number", direction: "asc" });

    const desc = getNextSortState(asc, "number");
    expect(desc).toEqual({ key: "number", direction: "desc" });

    expect(getNextSortState(desc, "number")).toBeNull();
  });
});

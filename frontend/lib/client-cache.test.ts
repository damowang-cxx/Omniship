import { beforeEach, describe, expect, it } from "vitest";
import {
  clearClientCache,
  invalidateWaybillCaches,
  isCacheFresh,
  readAccountCache,
  readWaybillCache,
  updateWaybillInCache,
  WAYBILL_REFRESH_INTERVAL_MS,
  writeAccountCache,
  writeWaybillCache
} from "./client-cache";
import type { AppUser, WaybillItem } from "./types";

const admin: AppUser = {
  id: "admin-id",
  email: "admin@example.com",
  username: "Admin",
  role: "admin",
  status: "active",
  balance: "0.00",
  createdAt: "2026-07-16T10:00:00Z",
  updatedAt: "2026-07-16T10:00:00Z"
};

const waybill = {
  id: "waybill-id",
  publicCode: "A7K2P9QX",
  uploadId: "upload-id",
  userId: "user-id",
  number: "784-84063276",
  status: "created",
  statusChangedAt: "2026-07-16T10:00:00Z",
  weightKg: "12.500",
  pieces: 8,
  receivedCount: 0,
  receivedTotal: 8,
  inWarehouseCount: 0,
  palletCount: 0,
  releasedCount: 0,
  outboundCount: 0,
  createdAt: "2026-07-16T10:00:00Z",
  updatedAt: "2026-07-16T10:00:00Z",
  podFiles: []
} satisfies WaybillItem;

describe("client cache", () => {
  beforeEach(() => sessionStorage.clear());

  it("isolates waybill lists by account and filters", () => {
    writeAccountCache(admin);
    writeWaybillCache(admin, {}, [waybill]);
    writeWaybillCache(admin, { status: "cleared" }, [{ ...waybill, status: "cleared" }]);

    expect(readWaybillCache(admin, {})?.data[0].status).toBe("created");
    expect(readWaybillCache(admin, { status: "cleared" })?.data[0].status).toBe("cleared");

    const nextUser = { ...admin, id: "other-id", email: "other@example.com" };
    writeAccountCache(nextUser);
    expect(readWaybillCache(admin, {})).toBeNull();
    expect(readAccountCache()?.data.id).toBe("other-id");
  });

  it("tracks the five-minute freshness window", () => {
    writeWaybillCache(admin, {}, [waybill], 1_000);
    const snapshot = readWaybillCache(admin, {});
    expect(snapshot).not.toBeNull();
    expect(isCacheFresh(snapshot!, 1_000 + WAYBILL_REFRESH_INTERVAL_MS - 1)).toBe(true);
    expect(isCacheFresh(snapshot!, 1_000 + WAYBILL_REFRESH_INTERVAL_MS)).toBe(false);
  });

  it("updates matching cached entries and supports invalidation", () => {
    writeWaybillCache(admin, {}, [waybill]);
    writeWaybillCache(admin, { status: "created" }, [waybill]);
    updateWaybillInCache({ ...waybill, airportOfArrival: "FRA" });
    expect(readWaybillCache(admin, {})?.data[0].airportOfArrival).toBe("FRA");
    expect(readWaybillCache(admin, { status: "created" })).toBeNull();

    invalidateWaybillCaches();
    expect(readWaybillCache(admin, {})).toBeNull();
  });

  it("discards malformed cache data and clears only application entries", () => {
    sessionStorage.setItem("epix.session-cache.v1.account", "not-json");
    sessionStorage.setItem("unrelated", "keep");
    expect(readAccountCache()).toBeNull();
    clearClientCache();
    expect(sessionStorage.getItem("unrelated")).toBe("keep");
  });
});

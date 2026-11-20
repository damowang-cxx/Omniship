import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { loginAsCustomer, returnToAdmin } from "./api";
import { readAccountCache, writeAccountCache } from "./client-cache";
import type { AppUser } from "./types";

const admin: AppUser = {
  id: "admin-id", email: "admin@example.com", username: "Admin", role: "admin", status: "active",
  balance: "0.00", createdAt: "2026-11-20T00:00:00Z", updatedAt: "2026-11-20T00:00:00Z"
};
const customer: AppUser = { ...admin, id: "customer-id", role: "user", impersonating: true };
const fetchMock = vi.fn();
function respond(user: AppUser) {
  fetchMock.mockResolvedValue(new Response(JSON.stringify({ user }), { status: 200 }));
}
function cacheData() {
  sessionStorage.setItem("epix.session-cache.v1.waybills.old", "old waybills");
  sessionStorage.setItem("epix.session-cache.v1.users.old", "old users");
}

describe("customer session API", () => {
  beforeEach(() => {
    sessionStorage.clear();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("enters the selected customer and clears administrator data caches", async () => {
    writeAccountCache(admin);
    cacheData();
    respond(customer);
    await loginAsCustomer(customer.id);
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/auth/impersonation"), expect.objectContaining({
      method: "POST", credentials: "include", body: JSON.stringify({ userId: customer.id })
    }));
    expect(readAccountCache()?.data).toEqual(customer);
    expect(sessionStorage.getItem("epix.session-cache.v1.waybills.old")).toBeNull();
    expect(sessionStorage.getItem("epix.session-cache.v1.users.old")).toBeNull();
  });

  it("restores the administrator and clears customer data caches", async () => {
    writeAccountCache(customer);
    cacheData();
    respond(admin);
    await returnToAdmin();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/auth/impersonation"), expect.objectContaining({
      method: "DELETE", credentials: "include"
    }));
    expect(readAccountCache()?.data).toEqual(admin);
    expect(sessionStorage.getItem("epix.session-cache.v1.waybills.old")).toBeNull();
  });

  it("preserves the active account when the server rejects a switch", async () => {
    writeAccountCache(admin);
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "Admin permission required" }), { status: 403 }));
    await expect(loginAsCustomer(customer.id)).rejects.toThrow("Admin permission required");
    expect(readAccountCache()?.data).toEqual(admin);
  });
});

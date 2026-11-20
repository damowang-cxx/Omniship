import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";
import type { AppUser } from "@/lib/types";

const router = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn() }));
const api = vi.hoisted(() => ({
  returnToAdmin: vi.fn(), listDownstreamIncidents: vi.fn(), markDownstreamIncidentsRead: vi.fn()
}));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api", () => api);

const user: AppUser = {
  id: "customer-id", email: "customer@example.com", username: "Customer", role: "user",
  status: "active", balance: "0.00", createdAt: "2026-11-20T00:00:00Z", updatedAt: "2026-11-20T00:00:00Z"
};
function show(account = user) {
  return render(<AppShell user={account} active="waybills" messages={[]} unreadCount={0} isInfoOpen={false}
    onInfoOpen={vi.fn()} onInfoClose={vi.fn()} onLogout={vi.fn()}><p>Customer waybills</p></AppShell>);
}

describe("customer session banner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.returnToAdmin.mockResolvedValue({ user: { ...user, role: "admin", impersonating: false } });
  });

  it("does not show return controls to a normal customer", () => {
    show();
    expect(screen.queryByRole("button", { name: "返回管理员" })).not.toBeInTheDocument();
  });

  it("shows the current customer with customer navigation and returns to Users", async () => {
    show({ ...user, impersonating: true });
    expect(screen.getByRole("region", { name: "客户登录状态" })).toHaveTextContent(user.email);
    expect(screen.queryByRole("link", { name: "Users" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Billing" })).toBeInTheDocument();
    expect(api.listDownstreamIncidents).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "返回管理员" }));
    await waitFor(() => {
      expect(api.returnToAdmin).toHaveBeenCalledTimes(1);
      expect(router.replace).toHaveBeenCalledWith("/users");
      expect(router.refresh).toHaveBeenCalled();
    });
  });

  it("keeps the return control available after a failed request", async () => {
    api.returnToAdmin.mockRejectedValueOnce(new Error("Network unavailable"));
    show({ ...user, impersonating: true });
    fireEvent.click(screen.getByRole("button", { name: "返回管理员" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Network unavailable");
    expect(screen.getByRole("button", { name: "返回管理员" })).toBeEnabled();
    expect(router.replace).not.toHaveBeenCalled();
  });
});

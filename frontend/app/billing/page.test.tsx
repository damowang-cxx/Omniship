import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BillingPage from "./page";

const routerMock = vi.hoisted(() => ({ replace: vi.fn() }));
const apiMock = vi.hoisted(() => ({
  getMyBillingAccount: vi.fn(),
  isUnauthorizedError: vi.fn((error: unknown) =>
    error instanceof Error && error.message.includes("401")
  ),
  logout: vi.fn()
}));

vi.mock("next/navigation", () => ({ useRouter: () => routerMock }));
vi.mock("@/lib/api", () => apiMock);

const user = {
  id: "user-id",
  email: "user@example.com",
  username: "User",
  role: "user",
  status: "active",
  balance: "94.00",
  createdAt: "2026-05-11T10:00:00Z",
  updatedAt: "2026-07-16T10:00:00Z"
};

describe("BillingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getMyBillingAccount.mockResolvedValue({
      user,
      deductions: [
        {
          id: "deduction-id",
          entryType: "deduction",
          amount: "6.00",
          currency: "EUR",
          balanceAfter: "94.00",
          waybillNumber: "784-84063276",
          billingSource: "retroactive",
          createdAt: "2026-07-16T10:00:00Z"
        }
      ],
      recharges: []
    });
  });

  it("shows balance and deduction entries for a customer", async () => {
    render(<BillingPage />);

    expect(await screen.findByRole("heading", { name: "Billing" })).toBeInTheDocument();
    expect(screen.getAllByText("€94.00").length).toBeGreaterThan(0);
    expect(screen.getByText("784-84063276")).toBeInTheDocument();
    expect(screen.getByText("Tax backfill")).toBeInTheDocument();
    expect(screen.getByText("€6.00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Billing" })).toHaveAttribute("href", "/billing");
  });

  it("refreshes the account", async () => {
    render(<BillingPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(apiMock.getMyBillingAccount).toHaveBeenCalledTimes(2));
  });
});

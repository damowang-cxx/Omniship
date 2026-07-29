import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import UsersPage from "./page";

const routerMock = vi.hoisted(() => ({ replace: vi.fn() }));

const apiMock = vi.hoisted(() => ({
  cancelDeduction: vi.fn(),
  createUser: vi.fn(),
  deleteUser: vi.fn(),
  exportBillingAccount: vi.fn(),
  getCurrentUser: vi.fn(),
  getRechargeReceiptUrl: vi.fn(
    (userId: string, entryId: string) => `/receipt/${userId}/${entryId}`
  ),
  getUserBillingAccount: vi.fn(),
  isUnauthorizedError: vi.fn((error: unknown) =>
    error instanceof Error && error.message.includes("401")
  ),
  listUsers: vi.fn(),
  logout: vi.fn(),
  rechargeUser: vi.fn(),
  resetUserPassword: vi.fn(),
  updateUserStatus: vi.fn()
}));

vi.mock("next/navigation", () => ({ useRouter: () => routerMock }));
vi.mock("@/lib/api", () => apiMock);

const adminUser = {
  id: "admin-id",
  email: "admin@example.com",
  username: "Admin",
  role: "admin",
  status: "active",
  balance: "0.00",
  createdAt: "2026-05-11T10:00:00Z",
  updatedAt: "2026-05-11T10:00:00Z"
};

const operatorUser = {
  id: "user-id",
  email: "operator@example.com",
  username: "Operator",
  role: "user",
  status: "active",
  balance: "0.00",
  createdAt: "2026-05-11T10:00:00Z",
  updatedAt: "2026-05-11T10:00:00Z"
};

describe("UsersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getCurrentUser.mockResolvedValue({ user: adminUser });
    apiMock.listUsers.mockResolvedValue({ items: [adminUser, operatorUser] });
    apiMock.getUserBillingAccount.mockResolvedValue({
      user: operatorUser,
      deductions: [],
      recharges: []
    });
    apiMock.exportBillingAccount.mockResolvedValue(
      "epix-billing-operator-20260729.xlsx"
    );
    apiMock.rechargeUser.mockResolvedValue({
      user: { ...operatorUser, balance: "25.00" },
      deductions: [],
      recharges: [
        {
          id: "recharge-id",
          entryType: "recharge",
          amount: "25.00",
          currency: "EUR",
          balanceAfter: "25.00",
          createdAt: "2026-07-16T10:00:00Z"
        }
      ]
    });
    apiMock.cancelDeduction.mockResolvedValue({
      user: { ...operatorUser, balance: "20.00" },
      deductions: [
        {
          id: "reversal-id",
          entryType: "deduction_reversal",
          amount: "15.00",
          currency: "EUR",
          balanceAfter: "20.00",
          waybillNumber: "784-84063276",
          supplierName: "QLS",
          supplierVersionNumber: 2,
          billableUnitCount: 5,
          unitRate: "3.00",
          billingSource: "cancellation",
          reversalOfEntryId: "deduction-id",
          createdAt: "2026-07-27T11:00:00Z"
        },
        {
          id: "deduction-id",
          entryType: "deduction",
          amount: "15.00",
          currency: "EUR",
          balanceAfter: "5.00",
          waybillNumber: "784-84063276",
          supplierName: "QLS",
          supplierVersionNumber: 2,
          billableUnitCount: 5,
          unitRate: "3.00",
          billingSource: "upload",
          reversedByEntryId: "reversal-id",
          createdAt: "2026-07-27T10:00:00Z"
        }
      ],
      recharges: []
    });
    apiMock.createUser.mockResolvedValue({ id: "new-user" });
    apiMock.deleteUser.mockResolvedValue({ status: "deleted" });
    apiMock.updateUserStatus.mockResolvedValue({ id: "user-id" });
    apiMock.resetUserPassword.mockResolvedValue({ id: "user-id" });
  });

  it("renders the balance column and linked email for admin", async () => {
    render(<UsersPage />);

    expect(await screen.findByRole("heading", { name: "Users" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Balance" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "operator@example.com" })).toBeInTheDocument();
  });

  it("creates a regular user", async () => {
    render(<UsersPage />);

    fireEvent.change(await screen.findByLabelText("Email"), {
      target: { value: "new@example.com" }
    });
    fireEvent.change(screen.getByLabelText("Username"), {
      target: { value: "New User" }
    });
    fireEvent.change(screen.getByLabelText("Initial password"), {
      target: { value: "password123" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Create user" }));

    await waitFor(() => {
      expect(apiMock.createUser).toHaveBeenCalledWith({
        email: "new@example.com",
        username: "New User",
        password: "password123"
      });
    });
  });

  it("deletes a user after confirmation", async () => {
    const confirmMock = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<UsersPage />);

    const userRow = (await screen.findByRole("button", { name: "operator@example.com" })).closest("tr");
    fireEvent.click(within(userRow as HTMLElement).getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(confirmMock).toHaveBeenCalledWith("Delete user operator@example.com?");
      expect(apiMock.deleteUser).toHaveBeenCalledWith("user-id");
      expect(apiMock.listUsers).toHaveBeenCalledTimes(2);
    });
    confirmMock.mockRestore();
  });

  it("opens customer details and adds a recharge", async () => {
    render(<UsersPage />);

    fireEvent.click(await screen.findByRole("button", { name: "operator@example.com" }));
    expect(await screen.findByRole("dialog", { name: "User details" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Recharge records" }));
    fireEvent.click(screen.getByRole("button", { name: "Recharge" }));
    fireEvent.change(screen.getByLabelText("Recharge amount (EUR)"), {
      target: { value: "25.00" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Add recharge" }));

    await waitFor(() => {
      expect(apiMock.rechargeUser).toHaveBeenCalledWith("user-id", "25.00", null);
    });
    expect(await screen.findByText("+€25.00")).toBeInTheDocument();
  });

  it("exports the selected customer's deduction entries", async () => {
    render(<UsersPage />);

    fireEvent.click(await screen.findByRole("button", { name: "operator@example.com" }));
    fireEvent.click(await screen.findByRole("button", { name: "Export Excel" }));

    await waitFor(() => {
      expect(apiMock.exportBillingAccount).toHaveBeenCalledWith("user-id");
    });
  });

  it("cancels a deduction and displays the refund as an audit entry", async () => {
    const deduction = {
      id: "deduction-id",
      entryType: "deduction",
      amount: "15.00",
      currency: "EUR",
      balanceAfter: "5.00",
      waybillNumber: "784-84063276",
      supplierName: "QLS",
      supplierVersionNumber: 2,
      billableUnitCount: 5,
      unitRate: "3.00",
      billingSource: "upload",
      createdAt: "2026-07-27T10:00:00Z"
    };
    apiMock.getUserBillingAccount.mockResolvedValueOnce({
      user: { ...operatorUser, balance: "5.00" },
      deductions: [deduction],
      recharges: []
    });
    const confirmMock = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<UsersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "operator@example.com" }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel tax" }));

    await waitFor(() => {
      expect(apiMock.cancelDeduction).toHaveBeenCalledWith(
        "user-id",
        "deduction-id"
      );
    });
    expect(confirmMock).toHaveBeenCalledWith(
      "Cancel customs tax for 784-84063276? €15.00 will be returned to the customer balance."
    );
    expect(await screen.findByText("Tax cancelled")).toBeInTheDocument();
    expect(screen.getByText("+€15.00")).toBeInTheDocument();
    expect(screen.getByText("Cancelled")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel tax" })).not.toBeInTheDocument();
    confirmMock.mockRestore();
  });

  it("redirects unauthenticated users to the public landing page", async () => {
    apiMock.getCurrentUser.mockRejectedValueOnce(new Error("Request failed with 401"));
    render(<UsersPage />);
    await waitFor(() => expect(routerMock.replace).toHaveBeenCalledWith("/"));
  });
});

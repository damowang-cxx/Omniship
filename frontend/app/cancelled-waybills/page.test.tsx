import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CancelledWaybillsPage from "./page";

const routerMock = vi.hoisted(() => ({ replace: vi.fn() }));
const apiMock = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  isUnauthorizedError: vi.fn(() => false),
  listCancelledWaybills: vi.fn(),
  logout: vi.fn()
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
  createdAt: "2026-07-01T10:00:00Z",
  updatedAt: "2026-07-01T10:00:00Z"
};

const record = {
  id: "cancel-id",
  originalUploadId: "upload-id",
  userId: "user-id",
  userEmail: "customer@example.com",
  username: "Customer",
  supplierId: "supplier-id",
  supplierName: "QLS",
  supplierVersionNumber: 3,
  shipmentType: "Air",
  airWaybillNumber: "784-84063276",
  grossWeightKg: "12.500",
  pieces: 8,
  airportOfDeparture: "HKG",
  airportOfArrival: "AMS",
  originalStatus: "approved",
  uploadedAt: "2026-07-20T10:00:00Z",
  fileCount: 2,
  taxAmountDeleted: "15.00",
  refundedAmount: "15.00",
  balanceAfterRefund: "35.00",
  currency: "EUR",
  reason: "Incorrect Pre Alert file",
  cancelledByUserId: "admin-id",
  cancelledByEmail: "admin@example.com",
  cancelledAt: "2026-07-28T10:00:00Z"
};

describe("CancelledWaybillsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getCurrentUser.mockResolvedValue({ user: adminUser });
    apiMock.listCancelledWaybills.mockResolvedValue({ items: [record] });
  });

  it("shows cancellation audit records and refund totals to admins", async () => {
    render(<CancelledWaybillsPage />);

    expect(
      await screen.findByRole("heading", { name: "Cancelled Waybills" })
    ).toBeInTheDocument();
    expect(screen.getByText("784-84063276")).toBeInTheDocument();
    expect(screen.getByText("Incorrect Pre Alert file")).toBeInTheDocument();
    expect(screen.getByText("customer@example.com")).toBeInTheDocument();
    expect(screen.getAllByText("€15.00").length).toBeGreaterThan(0);
  });

  it("refreshes cancellation records", async () => {
    render(<CancelledWaybillsPage />);
    expect(await screen.findByText("784-84063276")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => {
      expect(apiMock.listCancelledWaybills).toHaveBeenCalledTimes(2);
    });
  });

  it("redirects regular users", async () => {
    apiMock.getCurrentUser.mockResolvedValueOnce({
      user: { ...adminUser, role: "user" }
    });

    render(<CancelledWaybillsPage />);
    await waitFor(() => {
      expect(routerMock.replace).toHaveBeenCalledWith("/waybills");
    });
    expect(apiMock.listCancelledWaybills).not.toHaveBeenCalled();
  });
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InvoicePanel } from "./InvoicePanel";

const api = vi.hoisted(() => ({
  getMyInvoiceableDeductions: vi.fn(),
  listMyInvoices: vi.fn(),
  createMyInvoices: vi.fn(),
  downloadMyInvoices: vi.fn()
}));
vi.mock("@/lib/api", () => api);

describe("Invoice fee lines", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listMyInvoices.mockResolvedValue([]);
    api.getMyInvoiceableDeductions.mockResolvedValue([
      { id: "tax", waybillNumber: "784-123", feeType: "customs_tax", feeName: "Customs tax", quantity: 2, unitRate: "3.00", amount: "6.00", extraFeeTotal: "12.50", totalAmount: "18.50" },
      { id: "operation", waybillNumber: "784-123", feeType: "declaration_operation_fee", feeName: "申报行操作费", quantity: 10, unitRate: "2.00", amount: "20.00", extraFeeTotal: "0.00", totalAmount: "20.00" }
    ]);
    api.createMyInvoices.mockResolvedValue({ invoices: [{ id: "invoice" }] });
    api.downloadMyInvoices.mockResolvedValue(undefined);
  });

  it("selects two different fees for the same waybill without doubling extras", async () => {
    render(<InvoicePanel />);
    fireEvent.click(screen.getByRole("button", { name: "Create invoice" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select 784-123 Customs tax" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select 784-123 申报行操作费" }));
    expect(screen.getByRole("columnheader", { name: "Unit rate" })).toBeInTheDocument();
    expect(screen.getByText("€38.50")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Create & download" }));
    await waitFor(() => expect(api.createMyInvoices).toHaveBeenCalledWith(["tax", "operation"], expect.any(String)));
    expect(api.downloadMyInvoices).toHaveBeenCalledWith(["invoice"]);
  });
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SuppliersPage from "./page";

const routerMock = vi.hoisted(() => ({ replace: vi.fn() }));
const apiMock = vi.hoisted(() => ({
  applyRetroactiveBilling: vi.fn(),
  createSupplier: vi.fn(),
  getBillingSettings: vi.fn(),
  getCurrentUser: vi.fn(),
  isUnauthorizedError: vi.fn(() => false),
  listSuppliers: vi.fn(),
  logout: vi.fn(),
  publishSupplierVersion: vi.fn(),
  updateBillingSettings: vi.fn(),
  updateSupplier: vi.fn()
}));

vi.mock("next/navigation", () => ({ useRouter: () => routerMock }));
vi.mock("@/lib/api", () => apiMock);

const admin = {
  id: "admin-id",
  email: "admin@example.com",
  username: "Admin",
  role: "admin",
  status: "active",
  balance: "0.00",
  createdAt: "2026-07-16T10:00:00Z",
  updatedAt: "2026-07-16T10:00:00Z"
};

const qls = {
  id: "supplier-id",
  name: "QLS",
  status: "active",
  currentVersionNumber: 1,
  currentVersion: {
    id: "version-id",
    versionNumber: 1,
    config: {
      workbook: { sheetMode: "first", sheetName: null, headerRow: 1, dataStartRow: 2 },
      fields: [
        {
          key: "parcel",
          name: "Parcel Unit Number",
          semanticField: "parcel_unit_number",
          locatorMode: "column",
          locatorValue: "I",
          valueType: "text",
          blankPolicy: "skip_row",
          caseInsensitive: false,
          allowUnknownCountry: true,
          countryAliases: {},
          constraints: { allowedValues: [], unique: false }
        }
      ],
      rowKeyFieldKey: "parcel",
      billingGroupFieldKey: "parcel",
      billingDistinctFieldKey: "parcel"
    },
    createdAt: "2026-07-16T10:00:00Z"
  },
  createdAt: "2026-07-16T10:00:00Z",
  updatedAt: "2026-07-16T10:00:00Z"
};

describe("SuppliersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getCurrentUser.mockResolvedValue({ user: admin });
    apiMock.listSuppliers.mockResolvedValue({ items: [qls] });
    apiMock.getBillingSettings.mockResolvedValue({
      unitTaxEur: "3.00",
      taxableAirports: ["AMS"],
      taxEffectiveDate: "2026-07-01",
      updatedAt: "2026-07-16T10:00:00Z"
    });
    apiMock.updateBillingSettings.mockResolvedValue({
      unitTaxEur: "4.00",
      taxableAirports: ["AMS", "FRA"],
      taxEffectiveDate: "2026-07-01",
      updatedAt: "2026-07-16T10:00:00Z"
    });
    apiMock.applyRetroactiveBilling.mockResolvedValue({
      requestedCount: 2,
      succeededCount: 1,
      failedCount: 1,
      succeeded: [{
        waybillNumber: "784-84063276",
        supplierName: "QLS",
        supplierVersionNumber: 1,
        billableUnitCount: 5,
        unitRate: "3.00",
        amount: "15.00",
        balanceAfter: "-15.00",
        warningCount: 0
      }],
      failed: [{ waybillNumber: "MISSING-1", reason: "Waybill upload was not found" }]
    });
    apiMock.createSupplier.mockResolvedValue({ ...qls, id: "rpl-id", name: "RPL" });
  });

  it("shows billing policy and current suppliers", async () => {
    render(<SuppliersPage />);

    expect(await screen.findByRole("heading", { name: "Supplier" })).toBeInTheDocument();
    expect(screen.getByText("QLS")).toBeInTheDocument();
    expect(screen.getByDisplayValue("3.00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Supplier" })).toHaveAttribute("href", "/suppliers");
  });

  it("creates a supplier with the visual rule builder", async () => {
    render(<SuppliersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Add supplier" }));
    fireEvent.change(screen.getByLabelText("Supplier name"), { target: { value: "RPL" } });
    expect(screen.getByLabelText("Waybill number field")).toHaveValue("row_identifier");
    expect(screen.getByLabelText("Carton number field")).toHaveValue("row_identifier");
    fireEvent.click(screen.getByRole("button", { name: "Create supplier" }));

    await waitFor(() => {
      expect(apiMock.createSupplier).toHaveBeenCalledWith(
        "RPL",
        expect.objectContaining({
          rowKeyFieldKey: "row_identifier",
          billingGroupFieldKey: "row_identifier",
          billingDistinctFieldKey: "row_identifier"
        })
      );
    });
  });

  it("processes and summarizes retroactive customs deductions", async () => {
    render(<SuppliersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Tax backfill" }));
    fireEvent.change(screen.getByLabelText("Waybill numbers"), {
      target: { value: "784-84063276 MISSING-1" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Process backfill" }));

    await waitFor(() => {
      expect(apiMock.applyRetroactiveBilling).toHaveBeenCalledWith([
        "784-84063276",
        "MISSING-1"
      ]);
    });
    expect(await screen.findByText("Recorded deductions")).toBeInTheDocument();
    expect(screen.getByText("Waybill upload was not found")).toBeInTheDocument();
    expect(screen.getByText("€15.00")).toBeInTheDocument();
  });
});

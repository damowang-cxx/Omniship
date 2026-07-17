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
      billingGroupColumn: "I",
      billingDistinctColumn: "I"
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
    apiMock.publishSupplierVersion.mockResolvedValue(qls);
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
    fireEvent.change(screen.getByLabelText("Waybill number column"), { target: { value: "c" } });
    fireEvent.change(screen.getByLabelText("Carton number column"), { target: { value: "x" } });
    expect(screen.getByLabelText("Waybill number column")).toHaveValue("C");
    expect(screen.getByLabelText("Carton number column")).toHaveValue("X");
    expect(screen.getByLabelText(/Blank handling/)).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Create supplier" }));

    await waitFor(() => {
      expect(apiMock.createSupplier).toHaveBeenCalledWith(
        "RPL",
        expect.objectContaining({
          billingGroupColumn: "C",
          billingDistinctColumn: "X"
        })
      );
    });
  });

  it("keeps deduction columns independent from field-rule blank handling", async () => {
    const legacy = {
      ...qls,
      currentVersion: {
        ...qls.currentVersion,
        config: {
          workbook: qls.currentVersion.config.workbook,
          fields: qls.currentVersion.config.fields.map((field) => ({
            ...field,
            blankPolicy: "allow"
          })),
          rowKeyFieldKey: "parcel",
          billingGroupFieldKey: "parcel",
          billingDistinctFieldKey: "parcel"
        }
      }
    };
    apiMock.listSuppliers.mockResolvedValueOnce({ items: [legacy] });

    render(<SuppliersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit & publish" }));

    expect(screen.getByLabelText("Waybill number column")).toHaveValue("I");
    expect(screen.getByLabelText("Carton number column")).toHaveValue("I");
    expect(screen.getByLabelText(/Blank handling/)).toHaveValue("allow");
    expect(screen.getByLabelText(/Blank handling/)).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Publish new version" }));

    await waitFor(() => {
      expect(apiMock.publishSupplierVersion).toHaveBeenCalledWith(
        "supplier-id",
        expect.objectContaining({
          billingGroupColumn: "I",
          billingDistinctColumn: "I",
          fields: [
            expect.objectContaining({ key: "parcel", blankPolicy: "allow" })
          ]
        })
      );
    });
    const published = apiMock.publishSupplierVersion.mock.calls[0][1];
    expect(published).not.toHaveProperty("rowKeyFieldKey");
    expect(published).not.toHaveProperty("billingGroupFieldKey");
    expect(published).not.toHaveProperty("billingDistinctFieldKey");
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

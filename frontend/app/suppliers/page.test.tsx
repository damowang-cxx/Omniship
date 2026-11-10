import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SuppliersPage from "./page";

const routerMock = vi.hoisted(() => ({ replace: vi.fn() }));
const apiMock = vi.hoisted(() => ({
  applyRetroactiveBilling: vi.fn(),
  createSupplier: vi.fn(),
  getBillingSettings: vi.fn(),
  getCurrentUser: vi.fn(),
  getLhrBillingSettings: vi.fn(),
  isUnauthorizedError: vi.fn(() => false),
  listSuppliers: vi.fn(),
  listUsers: vi.fn(),
  logout: vi.fn(),
  publishSupplierVersion: vi.fn(),
  updateBillingSettings: vi.fn(),
  updateLhrBillingSettings: vi.fn(),
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
    apiMock.listUsers.mockResolvedValue({ items: [admin, { ...admin, id: "customer-id", username: "LHR Customer", email: "customer@example.com", role: "user" }] });
    apiMock.getLhrBillingSettings.mockResolvedValue({ config: null, version: 0 });
    apiMock.updateLhrBillingSettings.mockImplementation(async (config) => ({ config, version: 1 }));
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
    expect(screen.getByRole("heading", { name: "LHR 扣费配置" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建 LHR 扣费配置" })).toBeInTheDocument();
    expect(screen.getByText("LHR 专用收费")).toBeInTheDocument();
  });

  it("does not repeat AMS suppliers inside the global LHR container", async () => {
    apiMock.listSuppliers.mockResolvedValue({ items: [qls, { ...qls, id: "ed-id", name: "ED" }, { ...qls, id: "rpl-id", name: "RPL" }] });
    render(<SuppliersPage />);
    const lhrContainer = await screen.findByRole("region", { name: "LHR 扣费配置" });
    expect(within(lhrContainer).getByText("LHR 专用收费")).toBeInTheDocument();
    expect(within(lhrContainer).queryByText("ED")).not.toBeInTheDocument();
    expect(within(lhrContainer).queryByText("QLS")).not.toBeInTheDocument();
    expect(within(lhrContainer).queryByText("RPL")).not.toBeInTheDocument();
    expect(within(lhrContainer).getAllByRole("button", { name: "创建 LHR 扣费配置" })).toHaveLength(1);
  });

  it("creates a supplier with the visual rule builder", async () => {
    render(<SuppliersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Add supplier" }));
    expect(screen.queryByText("LHR 独立扣费")).not.toBeInTheDocument();
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

  it("saves global LHR customer pricing and a fixed terminal surcharge", async () => {
    render(<SuppliersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "创建 LHR 扣费配置" }));
    fireEvent.click(screen.getByRole("checkbox", { name: /启用 LHR 扣费配置/ }));
    fireEvent.change(screen.getByLabelText("每票金额 (EUR)"), { target: { value: "48.00" } });
    fireEvent.click(screen.getByRole("button", { name: "添加客户" }));
    fireEvent.change(screen.getByLabelText("客户"), { target: { value: "customer-id" } });
    fireEvent.change(screen.getByLabelText("每公斤报价 (GBP)"), { target: { value: "0.75" } });
    fireEvent.click(screen.getByRole("button", { name: "确认" }));
    expect(screen.getByText("£0.75 / kg")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "固定金额" }));
    fireEvent.change(screen.getByLabelText("规则名称"), { target: { value: "Menzies" } });
    fireEvent.change(screen.getByLabelText("提单前三位（逗号分隔）"), { target: { value: "205, 784" } });
    fireEvent.change(screen.getByLabelText("每票附加费 (GBP)"), { target: { value: "25.00" } });
    fireEvent.click(screen.getByRole("button", { name: "保存 LHR 扣费" }));
    await waitFor(() => expect(apiMock.updateLhrBillingSettings).toHaveBeenCalledWith({
        clearanceFeeEur: "48.00",
        customerRates: [{ userId: "customer-id", rateGbpPerKg: "0.75" }],
        surchargeRules: [{ name: "Menzies", mode: "fixed", prefixes: ["205", "784"], amountGbp: "25.00", bands: [] }]
    }));
    expect(apiMock.publishSupplierVersion).not.toHaveBeenCalled();
  });

  it("builds consecutive LHR weight bands", async () => {
    render(<SuppliersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "创建 LHR 扣费配置" }));
    fireEvent.click(screen.getByRole("checkbox", { name: /启用 LHR 扣费配置/ }));
    fireEvent.click(screen.getByRole("button", { name: "重量段" }));
    fireEvent.change(screen.getByLabelText("规则名称"), { target: { value: "Swissport" } });
    fireEvent.change(screen.getByLabelText("提单前三位（逗号分隔）"), { target: { value: "016, 180" } });
    fireEvent.change(screen.getByLabelText("结束 kg"), { target: { value: "500" } });
    fireEvent.change(screen.getByLabelText("附加费 (GBP)"), { target: { value: "25.00" } });
    fireEvent.click(screen.getByRole("button", { name: "添加重量段" }));
    expect(screen.getAllByLabelText("起始 kg")[1]).toHaveValue(501);
    fireEvent.change(screen.getAllByLabelText("附加费 (GBP)")[1], { target: { value: "30.00" } });
    fireEvent.click(screen.getByRole("button", { name: "保存 LHR 扣费" }));
    await waitFor(() => expect(apiMock.updateLhrBillingSettings).toHaveBeenCalledWith(expect.objectContaining({ surchargeRules: [expect.objectContaining({
        mode: "weight_bands", prefixes: ["016", "180"], bands: [
          { minWeightKg: 0, maxWeightKg: 500, amountGbp: "25.00" },
          { minWeightKg: 501, maxWeightKg: null, amountGbp: "30.00" }
        ]
      })] })));
  });

  it("edits existing LHR fees only in the separate configuration area", async () => {
    apiMock.getLhrBillingSettings.mockResolvedValue({ config: { clearanceFeeEur: "45.00", customerRates: [{ userId: "customer-id", rateGbpPerKg: "0.50" }], surchargeRules: [] }, version: 2 });
    render(<SuppliersPage />);
    expect(await screen.findByRole("button", { name: "管理 LHR 扣费" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit & publish" }));
    expect(screen.queryByText("LHR 独立扣费")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close supplier editor" }));
    fireEvent.click(screen.getByRole("button", { name: "管理 LHR 扣费" }));
    expect(screen.getByLabelText("每票金额 (EUR)")).toHaveValue(45);
    expect(screen.getByText("£0.50 / kg")).toBeInTheDocument();
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

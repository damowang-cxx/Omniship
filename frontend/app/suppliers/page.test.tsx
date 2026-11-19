import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SuppliersPage from "./page";

const routerMock = vi.hoisted(() => ({ replace: vi.fn() }));
const apiMock = vi.hoisted(() => ({
  applyRetroactiveBilling: vi.fn(),
  createSupplier: vi.fn(),
  getBillingSettings: vi.fn(),
  getCurrentUser: vi.fn(),
  getAmsBillingSettings: vi.fn(),
  getLhrBillingSettings: vi.fn(),
  isUnauthorizedError: vi.fn(() => false),
  listSuppliers: vi.fn(),
  listUsers: vi.fn(),
  logout: vi.fn(),
  publishSupplierVersion: vi.fn(),
  updateBillingSettings: vi.fn(),
  updateAmsBillingSettings: vi.fn(),
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
    apiMock.getAmsBillingSettings.mockResolvedValue({ config: null, version: 0 });
    apiMock.updateAmsBillingSettings.mockImplementation(async (config) => ({ config, version: 1 }));
    apiMock.updateLhrBillingSettings.mockImplementation(async (config) => ({ config, version: 1 }));
    apiMock.getBillingSettings.mockResolvedValue({
      unitTaxEur: "3.00",
      amsTaxHandlingFeeEur: "8.00",
      taxableAirports: ["AMS"],
      taxEffectiveDate: "2026-07-01",
      updatedAt: "2026-07-16T10:00:00Z"
    });
    apiMock.updateBillingSettings.mockResolvedValue({
      unitTaxEur: "4.00",
      amsTaxHandlingFeeEur: "9.50",
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
    expect(screen.getByText("AMS 重量附加费未配置")).toBeInTheDocument();
    expect(screen.getByLabelText("AMS 税金手续费 (EUR / 票)")).toHaveValue(8);
    expect(screen.getByRole("button", { name: "创建 LHR 扣费配置" })).toBeInTheDocument();
    expect(screen.getByText("LHR 专用收费")).toBeInTheDocument();
  });

  it("saves the global AMS per-waybill fee beside unit tax without publishing a template", async () => {
    render(<SuppliersPage />);
    const fee = await screen.findByLabelText("AMS 税金手续费 (EUR / 票)");
    const form = fee.closest("form")!;
    expect(within(form).getByLabelText("Unit tax (EUR)")).toBeInTheDocument();
    expect(fee).toHaveAccessibleDescription("所有 AMS 客户，每票收取一次；0 表示不收取");
    fireEvent.change(fee, { target: { value: "9.50" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save policy" }));
    await waitFor(() => expect(apiMock.updateBillingSettings).toHaveBeenCalledWith("3.00", ["AMS"], "2026-07-01", "9.50"));
    expect(await screen.findByText("Billing settings saved")).toBeInTheDocument();
    expect(fee).toHaveValue(9.5);
    expect(apiMock.publishSupplierVersion).not.toHaveBeenCalled();
  });

  it("publishes template-specific AMS columns and multiple customer prices", async () => {
    render(<SuppliersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit & publish" }));
    const ams = screen.getByRole("region", { name: "模板 AMS 扣费配置" });
    fireEvent.click(within(ams).getByRole("checkbox", { name: "启用本模板 AMS 重量附加费" }));
    expect(within(ams).queryByLabelText("模板 AMS 每票税金手续费")).not.toBeInTheDocument();
    fireEvent.change(within(ams).getByLabelText("AMS 指定匹配列"), { target: { value: "e" } });
    fireEvent.change(within(ams).getByLabelText("AMS 匹配列标题"), { target: { value: "NETWORK" } });
    fireEvent.change(within(ams).getByLabelText("AMS 重量列"), { target: { value: "v" } });
    for (const value of ["DE-DHL", "Colissimo"]) {
      fireEvent.change(within(ams).getByLabelText("新增 AMS 明细值"), { target: { value } });
      fireEvent.click(within(ams).getByRole("button", { name: "添加明细选项" }));
    }
    fireEvent.change(within(ams).getByLabelText("AMS 添加客户"), { target: { value: "customer-id" } });
    for (const [value, price] of [["DE-DHL", "0.75"], ["Colissimo", "1.20"]]) {
      fireEvent.click(within(ams).getByRole("checkbox", { name: `LHR Customer 收取 ${value}` }));
      fireEvent.change(within(ams).getByLabelText(`LHR Customer ${value} 每公斤报价`), { target: { value: price } });
    }
    fireEvent.click(screen.getByRole("button", { name: "Publish new version" }));
    await waitFor(() => expect(apiMock.publishSupplierVersion).toHaveBeenCalledWith("supplier-id", expect.objectContaining({
      amsBilling: {
        matchColumn: "E", matchHeader: "NETWORK", weightColumn: "V",
        matchValues: ["DE-DHL", "Colissimo"],
        customerRates: [{ userId: "customer-id", fees: [
          { matchValue: "DE-DHL", rateEurPerKg: "0.75" }, { matchValue: "Colissimo", rateEurPerKg: "1.20" }
        ] }]
      }
    })));
    expect(apiMock.updateAmsBillingSettings).not.toHaveBeenCalled();
  });

  it("selects customer details immediately and preserves different prices for the same detail after publishing", async () => {
    const customerA = { ...admin, id: "customer-a", username: "Customer A", email: "a@example.com", role: "user" };
    const customerB = { ...admin, id: "customer-b", username: "Customer B", email: "b@example.com", role: "user" };
    apiMock.listUsers.mockResolvedValue({ items: [admin, customerA, customerB] });
    apiMock.publishSupplierVersion.mockImplementationOnce(async (_id, config) => {
      const updated = { ...qls, currentVersion: { ...qls.currentVersion, config } };
      apiMock.listSuppliers.mockResolvedValue({ items: [updated] });
      return updated;
    });
    render(<SuppliersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit & publish" }));
    const ams = screen.getByRole("region", { name: "模板 AMS 扣费配置" });
    fireEvent.click(within(ams).getByRole("checkbox", { name: "启用本模板 AMS 重量附加费" }));
    expect(within(ams).getByLabelText("AMS 添加客户")).toBeDisabled();
    fireEvent.change(within(ams).getByLabelText("AMS 指定匹配列"), { target: { value: "E" } });
    fireEvent.change(within(ams).getByLabelText("AMS 重量列"), { target: { value: "V" } });
    for (const value of ["DE-DHL", "Colissimo"]) {
      fireEvent.change(within(ams).getByLabelText("新增 AMS 明细值"), { target: { value } });
      fireEvent.click(within(ams).getByRole("button", { name: "添加明细选项" }));
    }
    for (const [customer, price] of [[customerA, "0.75"], [customerB, "1.50"]] as const) {
      fireEvent.change(within(ams).getByLabelText("AMS 添加客户"), { target: { value: customer.id } });
      expect(within(ams).getByRole("group", { name: customer.username })).toBeInTheDocument();
      expect(within(ams).getByLabelText(`${customer.username} DE-DHL 每公斤报价`)).toBeDisabled();
      fireEvent.click(within(ams).getByRole("checkbox", { name: `${customer.username} 收取 DE-DHL` }));
      fireEvent.change(within(ams).getByLabelText(`${customer.username} DE-DHL 每公斤报价`), { target: { value: price } });
    }
    fireEvent.click(within(ams).getByRole("checkbox", { name: "Customer A 收取 Colissimo" }));
    fireEvent.change(within(ams).getByLabelText("Customer A Colissimo 每公斤报价"), { target: { value: "1.20" } });
    expect(within(ams).getByRole("checkbox", { name: "Customer B 收取 Colissimo" })).not.toBeChecked();
    expect(within(ams).getByLabelText("Customer B Colissimo 每公斤报价")).toBeDisabled();
    expect(within(ams).getByLabelText("Customer A DE-DHL 每公斤报价")).toHaveValue(0.75);
    expect(within(ams).getByLabelText("Customer B DE-DHL 每公斤报价")).toHaveValue(1.5);
    fireEvent.click(screen.getByRole("button", { name: "Publish new version" }));
    await waitFor(() => expect(apiMock.publishSupplierVersion).toHaveBeenCalledWith("supplier-id", expect.objectContaining({
      amsBilling: expect.objectContaining({ customerRates: expect.arrayContaining([
        { userId: "customer-a", fees: [{ matchValue: "DE-DHL", rateEurPerKg: "0.75" }, { matchValue: "Colissimo", rateEurPerKg: "1.20" }] },
        { userId: "customer-b", fees: [{ matchValue: "DE-DHL", rateEurPerKg: "1.50" }] }
      ]) })
    })));
    fireEvent.click(await screen.findByRole("button", { name: "Edit & publish" }));
    expect(screen.getByLabelText("Customer A DE-DHL 每公斤报价")).toHaveValue(0.75);
    expect(screen.getByLabelText("Customer B DE-DHL 每公斤报价")).toHaveValue(1.5);
    expect(screen.getByRole("checkbox", { name: "Customer A 收取 Colissimo" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Customer B 收取 Colissimo" })).not.toBeChecked();
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

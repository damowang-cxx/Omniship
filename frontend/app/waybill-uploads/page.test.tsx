import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WaybillUploadsPage from "./page";

const routerMock = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn()
}));

const apiMock = vi.hoisted(() => ({
  deleteWaybillUpload: vi.fn(),
  estimatePreAlertTax: vi.fn(),
  getWaybillUploadFileDownloadUrl: vi.fn(
    (uploadId: string, fileId: string) =>
      `/backend/v1/waybill-uploads/${uploadId}/files/${fileId}/download`
  ),
  getCurrentUser: vi.fn(),
  isUnauthorizedError: vi.fn((error: unknown) =>
    error instanceof Error && error.message.includes("401")
  ),
  listUsers: vi.fn(),
  listSuppliers: vi.fn(),
  listWaybillUploads: vi.fn(),
  logout: vi.fn(),
  uploadPreAlertFile: vi.fn()
}));

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock
}));

vi.mock("@/lib/api", () => apiMock);

const regularUser = {
  id: "user-id",
  email: "user@example.com",
  username: "User",
  role: "user",
  status: "active",
  balance: "120.00",
  createdAt: "2026-05-11T10:00:00Z",
  updatedAt: "2026-05-11T10:00:00Z"
};

const adminUser = {
  ...regularUser,
  id: "admin-id",
  email: "admin@example.com",
  username: "Admin",
  role: "admin"
};

const supplier = {
  id: "supplier-id",
  name: "QLS",
  status: "active",
  currentVersionNumber: 1,
  currentVersion: {
    id: "supplier-version-id",
    versionNumber: 1,
    config: {
      workbook: { sheetMode: "first", headerRow: 1, dataStartRow: 2 },
      fields: [],
      rowKeyFieldKey: "parcel",
      billingDistinctFieldKey: "parcel"
    },
    createdAt: "2026-07-16T10:00:00Z"
  },
  createdAt: "2026-07-16T10:00:00Z",
  updatedAt: "2026-07-16T10:00:00Z"
};

const uploadItem = {
  id: "upload-id",
  userId: "user-id",
  uploadedByUserId: "user-id",
  shipmentType: "Air",
  airWaybillNumber: "784-84063276",
  grossWeightKg: "12.500",
  pieces: 8,
  arrivalFlightNumber: "EK0147",
  airportOfDeparture: "HKG",
  airportOfArrival: "AMS",
  status: "pending_review",
  createdAt: "2026-05-11T10:00:00Z",
  updatedAt: "2026-05-11T10:00:00Z",
  user: {
    id: "user-id",
    email: "user@example.com",
    username: "User"
  },
  uploadedBy: {
    id: "user-id",
    email: "user@example.com",
    username: "User"
  },
  files: [
    {
      id: "file-id",
      fileKind: "air_waybill_document",
      originalFilename: "awb.pdf",
      sizeBytes: 128,
      sha256: "hash",
      createdAt: "2026-05-11T10:00:00Z"
    }
  ]
};

function fillRequiredFields() {
  fireEvent.change(screen.getByLabelText("Air Waybill Number"), {
    target: { value: "784-84063276" }
  });
  fireEvent.change(screen.getByLabelText("Air Waybill Gross Weight (KG)"), {
    target: { value: "12.5" }
  });
  fireEvent.change(screen.getByLabelText("Air Waybill Pieces"), {
    target: { value: "8" }
  });
  fireEvent.change(screen.getByLabelText("Arrival Flight Number"), {
    target: { value: "EK0147" }
  });
  fireEvent.change(screen.getByLabelText("Airport of Departure"), {
    target: { value: "HKG" }
  });
  fireEvent.change(screen.getByLabelText("Airport of Arrival"), {
    target: { value: "AMS" }
  });
  fireEvent.change(screen.getByLabelText("Air Waybill Document(s)"), {
    target: {
      files: [new File(["%PDF-1.4"], "awb.pdf", { type: "application/pdf" })]
    }
  });
  fireEvent.change(screen.getByLabelText("Upload Pre Alert File"), {
    target: {
      files: [
        new File(["excel workbook"], "pre-alert.xlsx", {
          type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        })
      ]
    }
  });
}

describe("WaybillUploadsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    apiMock.getCurrentUser.mockResolvedValue({ user: regularUser });
    apiMock.listWaybillUploads.mockResolvedValue({ items: [] });
    apiMock.listUsers.mockResolvedValue({ items: [adminUser, regularUser] });
    apiMock.listSuppliers.mockResolvedValue({ items: [supplier] });
    apiMock.uploadPreAlertFile.mockResolvedValue({
      uploadId: "upload-id",
      airWaybillNumber: "784-84063276",
      airportOfDeparture: "HKG",
      airportOfArrival: "AMS",
      status: "pending_review",
      boundUserId: "user-id",
      supplierId: "supplier-id",
      supplierName: "QLS",
      supplierVersionNumber: 1,
      billableUnitCount: 2,
      unitRate: "3.00",
      deductedTax: "6.00",
      balanceAfter: "114.00",
      validationIssueCount: 0,
      validationIssues: []
    });
    apiMock.estimatePreAlertTax.mockResolvedValue({
      supplierId: "supplier-id",
      supplierName: "QLS",
      supplierVersionId: "supplier-version-id",
      supplierVersionNumber: 1,
      taxableAirport: true,
      billableUnitCount: 2,
      unitRate: "3.00",
      estimatedTax: "6.00",
      warningCount: 0,
      warnings: [],
      currency: "EUR"
    });
    apiMock.deleteWaybillUpload.mockResolvedValue({
      status: "deleted",
      uploadId: "upload-id"
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("uploads a pre alert for the current user", async () => {
    render(<WaybillUploadsPage />);

    expect(await screen.findByRole("heading", { name: "Upload Pre Alert" })).toBeInTheDocument();
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: "Upload Pre Alert" }));

    await waitFor(() => {
      expect(apiMock.uploadPreAlertFile).toHaveBeenCalledTimes(1);
    });
    expect(apiMock.uploadPreAlertFile.mock.calls[0][0]).toMatchObject({
      shipmentType: "Air",
      airWaybillNumber: "784-84063276",
      grossWeightKg: "12.5",
      pieces: "8",
      arrivalFlightNumber: "EK0147",
      airportOfDeparture: "HKG",
      airportOfArrival: "AMS",
      supplierId: "supplier-id"
    });
    expect(
      await screen.findByText("Upload saved for 784-84063276. Tax deducted: €6.00")
    ).toBeInTheDocument();
    expect(screen.getByText("Select Pre Alert")).toBeInTheDocument();
    expect(screen.queryByText("€6.00")).not.toBeInTheDocument();
  });

  it("shows backend Excel validation errors in a dialog", async () => {
    apiMock.uploadPreAlertFile.mockRejectedValueOnce(
      new Error(
        "Request failed with 400: Pre Alert validation failed: 同一收件人/地址的 W 列申报金额超过 150 EUR: rows 2, 3, recipient Jane Doe, address 1 Test Street, total 150.01 EUR"
      )
    );

    render(<WaybillUploadsPage />);

    expect(await screen.findByRole("heading", { name: "Upload Pre Alert" })).toBeInTheDocument();
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: "Upload Pre Alert" }));

    expect(
      await screen.findByRole("dialog", { name: "Excel validation failed" })
    ).toBeInTheDocument();
    expect(screen.getAllByText(/W 列申报金额超过 150 EUR/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/rows 2, 3/).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "I understand" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("hides target user and management navigation for regular users", async () => {
    render(<WaybillUploadsPage />);

    expect(await screen.findByRole("heading", { name: "Upload Pre Alert" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Target User")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Waybill Management/ })).not.toBeInTheDocument();
  });

  it("shows target user and management navigation for admins", async () => {
    apiMock.getCurrentUser.mockResolvedValue({ user: adminUser });

    render(<WaybillUploadsPage />);

    expect(await screen.findByLabelText("Target User")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Waybill Management/ })).toHaveAttribute(
      "href",
      "/waybill-upload-management"
    );
    expect(screen.getByText("Manage submitted waybills")).toBeInTheDocument();
    expect(apiMock.listWaybillUploads).not.toHaveBeenCalled();
  });

  it("shows file download links in regular user upload details", async () => {
    apiMock.listWaybillUploads.mockResolvedValue({ items: [uploadItem] });

    render(<WaybillUploadsPage />);

    expect(await screen.findByText("784-84063276")).toBeInTheDocument();
    expect(screen.getByText("HKG")).toBeInTheDocument();
    expect(screen.getByText("AMS")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Details 784-84063276" }));

    const link = await screen.findByRole("link", {
      name: "Air Waybill Document: awb.pdf"
    });
    expect(link).toHaveAttribute(
      "href",
      "/backend/v1/waybill-uploads/upload-id/files/file-id/download"
    );
  });

  it("deletes a regular user upload record", async () => {
    apiMock.listWaybillUploads.mockResolvedValue({ items: [uploadItem] });

    render(<WaybillUploadsPage />);

    expect(await screen.findByText("784-84063276")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", {
        name: "Delete local upload 784-84063276"
      })
    );

    await waitFor(() => {
      expect(apiMock.deleteWaybillUpload).toHaveBeenCalledWith("upload-id");
    });
    expect(
      await screen.findByText("Upload deleted for 784-84063276")
    ).toBeInTheDocument();
  });

  it("validates required numeric fields before upload", async () => {
    render(<WaybillUploadsPage />);

    await screen.findByRole("heading", { name: "Upload Pre Alert" });
    fireEvent.change(screen.getByLabelText("Air Waybill Number"), {
      target: { value: "784-84063276" }
    });
    fireEvent.change(screen.getByLabelText("Air Waybill Gross Weight (KG)"), {
      target: { value: "not-a-number" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload Pre Alert" }));

    expect(
      (await screen.findAllByText("Air Waybill Gross Weight (KG) must be a number"))
        .length
    ).toBeGreaterThan(0);
    expect(apiMock.uploadPreAlertFile).not.toHaveBeenCalled();
  });

  it("redirects unauthenticated users to the public landing page", async () => {
    apiMock.getCurrentUser.mockRejectedValueOnce(new Error("Request failed with 401"));

    render(<WaybillUploadsPage />);

    await waitFor(() => {
      expect(routerMock.replace).toHaveBeenCalledWith("/");
    });
  });
});

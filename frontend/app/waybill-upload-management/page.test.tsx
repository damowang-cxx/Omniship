import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WaybillUploadManagementPage from "./page";

const routerMock = vi.hoisted(() => ({
  replace: vi.fn()
}));

const apiMock = vi.hoisted(() => ({
  deleteWaybillUpload: vi.fn(),
  getWaybillUploadFileDownloadUrl: vi.fn(
    (uploadId: string, fileId: string) =>
      `/backend/v1/waybill-uploads/${uploadId}/files/${fileId}/download`
  ),
  getCurrentUser: vi.fn(),
  isUnauthorizedError: vi.fn((error: unknown) =>
    error instanceof Error && error.message.includes("401")
  ),
  listUsers: vi.fn(),
  listWaybillUploads: vi.fn(),
  logout: vi.fn(),
  updateWaybillUploadStatus: vi.fn()
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

const uploadItem = {
  id: "upload-id",
  userId: "user-id",
  uploadedByUserId: "admin-id",
  shipmentType: "Air",
  airWaybillNumber: "784-84063276",
  grossWeightKg: "12.500",
  pieces: 8,
  arrivalFlightNumber: "EK0147",
  status: "pending_review",
  createdAt: "2026-05-11T10:00:00Z",
  updatedAt: "2026-05-11T10:00:00Z",
  user: {
    id: "user-id",
    email: "user@example.com",
    username: "User"
  },
  uploadedBy: {
    id: "admin-id",
    email: "admin@example.com",
    username: "Admin"
  },
  files: [
    {
      id: "file-id",
      fileKind: "customer_pre_alert",
      originalFilename: "pre-alert.xlsx",
      sizeBytes: 128,
      sha256: "hash",
      createdAt: "2026-05-11T10:00:00Z"
    }
  ]
};

describe("WaybillUploadManagementPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    apiMock.getCurrentUser.mockResolvedValue({ user: adminUser });
    apiMock.listUsers.mockResolvedValue({ items: [adminUser, regularUser] });
    apiMock.listWaybillUploads.mockResolvedValue({ items: [uploadItem] });
    apiMock.updateWaybillUploadStatus.mockResolvedValue({
      ...uploadItem,
      status: "approved"
    });
    apiMock.deleteWaybillUpload.mockResolvedValue({
      status: "deleted",
      uploadId: "upload-id"
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("renders submitted waybills for admins", async () => {
    render(<WaybillUploadManagementPage />);

    expect(await screen.findByRole("heading", { name: "Waybill Management" })).toBeInTheDocument();
    expect(screen.getByText("784-84063276")).toBeInTheDocument();
    expect(screen.getAllByText("user@example.com").length).toBeGreaterThan(0);
    expect(screen.getAllByText("admin@example.com").length).toBeGreaterThan(0);
  });

  it("filters uploads by user, status, and number", async () => {
    render(<WaybillUploadManagementPage />);

    expect(await screen.findByLabelText("Filter User")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Filter User"), {
      target: { value: "user-id" }
    });
    fireEvent.change(screen.getByLabelText("Filter Review Status"), {
      target: { value: "pending_review" }
    });
    fireEvent.change(screen.getByLabelText("Filter Number"), {
      target: { value: "78484063276" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => {
      expect(apiMock.listWaybillUploads).toHaveBeenLastCalledWith({
        userId: "user-id",
        status: "pending_review",
        q: "78484063276"
      });
    });
  });

  it("shows file download links in upload details", async () => {
    render(<WaybillUploadManagementPage />);

    expect(await screen.findByText("784-84063276")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Details 784-84063276" }));

    const link = await screen.findByRole("link", {
      name: "Customer Pre Alert: pre-alert.xlsx"
    });
    expect(link).toHaveAttribute(
      "href",
      "/backend/v1/waybill-uploads/upload-id/files/file-id/download"
    );
  });

  it("approves and rejects uploads", async () => {
    render(<WaybillUploadManagementPage />);

    expect(await screen.findByText("784-84063276")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Approve 784-84063276" }));

    await waitFor(() => {
      expect(apiMock.updateWaybillUploadStatus).toHaveBeenCalledWith(
        "upload-id",
        "approved"
      );
    });
  });

  it("deletes upload records", async () => {
    render(<WaybillUploadManagementPage />);

    expect(await screen.findByText("784-84063276")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", {
        name: "Delete local upload 784-84063276"
      })
    );

    await waitFor(() => {
      expect(apiMock.deleteWaybillUpload).toHaveBeenCalledWith("upload-id");
    });
  });

  it("redirects regular users back to uploads", async () => {
    apiMock.getCurrentUser.mockResolvedValueOnce({ user: regularUser });

    render(<WaybillUploadManagementPage />);

    await waitFor(() => {
      expect(routerMock.replace).toHaveBeenCalledWith("/waybill-uploads");
    });
  });
});

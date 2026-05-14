import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WaybillUploadsPage from "./page";

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
  manualSubmitWaybillUpload: vi.fn(),
  updateWaybillUploadStatus: vi.fn(),
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
  uploadedByUserId: "user-id",
  platform: "ALLINE",
  shipmentType: "Air",
  airWaybillNumber: "784-84063276",
  grossWeightKg: "12.500",
  pieces: 8,
  arrivalFlightNumber: "EK0147",
  status: "pending_review",
  platformSubmissionStatus: "success",
  platformSubmissionMethod: "automated",
  platformSubmissionError: null,
  platformSubmittedAt: "2026-05-11T10:00:08Z",
  createdAt: "2026-05-11T10:00:00Z",
  updatedAt: "2026-05-11T10:00:00Z",
  user: {
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
  fireEvent.change(screen.getByLabelText("Air Waybill Document(s)"), {
    target: {
      files: [new File(["%PDF-1.4"], "awb.pdf", { type: "application/pdf" })]
    }
  });
  fireEvent.change(screen.getByLabelText("Upload Pre Alert File"), {
    target: {
      files: [
        new File(["excel"], "pre-alert.xlsx", {
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
    apiMock.uploadPreAlertFile.mockResolvedValue({
      uploadId: "upload-id",
      platform: "ALLINE",
      airWaybillNumber: "784-84063276",
      status: "pending_review",
      platformSubmissionStatus: "success",
      platformSubmissionMethod: "automated",
      platformSubmissionError: null,
      platformSubmittedAt: "2026-05-11T10:00:08Z",
      boundUserId: "user-id"
    });
    apiMock.updateWaybillUploadStatus.mockResolvedValue({
      ...uploadItem,
      status: "approved"
    });
    apiMock.deleteWaybillUpload.mockResolvedValue({
      status: "deleted",
      uploadId: "upload-id",
      removedBinding: true
    });
    apiMock.manualSubmitWaybillUpload.mockResolvedValue({
      ...uploadItem,
      platformSubmissionMethod: "manual"
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("uploads a pre alert for the current user", async () => {
    render(<WaybillUploadsPage />);

    expect(await screen.findByRole("heading", { name: "Upload Pre Alert" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "ALLINE" })).toBeChecked();
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: "Upload Pre Alert" }));

    await waitFor(() => {
      expect(apiMock.uploadPreAlertFile).toHaveBeenCalledTimes(1);
    });
    expect(apiMock.uploadPreAlertFile.mock.calls[0][0]).toMatchObject({
      platform: "ALLINE",
      shipmentType: "Air",
      airWaybillNumber: "784-84063276",
      grossWeightKg: "12.5",
      pieces: "8",
      arrivalFlightNumber: "EK0147"
    });
    expect(await screen.findByText("Upload completed for 784-84063276")).toBeInTheDocument();
  });

  it("shows all uploaded records and review actions for admins", async () => {
    apiMock.getCurrentUser.mockResolvedValueOnce({ user: adminUser });
    apiMock.listWaybillUploads.mockResolvedValue({ items: [uploadItem] });

    render(<WaybillUploadsPage />);

    expect(await screen.findByText("784-84063276")).toBeInTheDocument();
    expect(screen.getAllByText("user@example.com").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Approve 784-84063276" }));

    await waitFor(() => {
      expect(apiMock.updateWaybillUploadStatus).toHaveBeenCalledWith(
        "upload-id",
        "approved"
      );
    });
  });

  it("lets admins filter uploads by user and number", async () => {
    apiMock.getCurrentUser.mockResolvedValueOnce({ user: adminUser });
    apiMock.listWaybillUploads.mockResolvedValue({ items: [uploadItem] });

    render(<WaybillUploadsPage />);

    expect(await screen.findByLabelText("Filter User")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Filter User"), {
      target: { value: "user-id" }
    });
    fireEvent.change(screen.getByLabelText("Filter Platform Upload"), {
      target: { value: "success" }
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
        platformSubmissionStatus: "success",
        status: "pending_review",
        q: "78484063276"
      });
    });
  });

  it("shows file download links in upload details", async () => {
    apiMock.listWaybillUploads.mockResolvedValue({ items: [uploadItem] });

    render(<WaybillUploadsPage />);

    expect(await screen.findByText("784-84063276")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Details 784-84063276" }));

    const link = await screen.findByRole("link", {
      name: "Air Waybill Document: awb.pdf"
    });
    expect(link).toHaveAttribute(
      "href",
      "/backend/v1/waybill-uploads/upload-id/files/file-id/download"
    );
  });

  it("lets admins manually confirm failed uploads", async () => {
    const failedUpload = {
      ...uploadItem,
      platformSubmissionStatus: "failed",
      platformSubmissionMethod: "automated",
      platformSubmissionError: "Upload records button not found"
    };
    apiMock.getCurrentUser.mockResolvedValueOnce({ user: adminUser });
    apiMock.listWaybillUploads.mockResolvedValue({ items: [failedUpload] });

    render(<WaybillUploadsPage />);

    expect(await screen.findByText("Failed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Manually submit 784-84063276" }));

    await waitFor(() => {
      expect(apiMock.manualSubmitWaybillUpload).toHaveBeenCalledWith("upload-id", false);
    });
  });

  it("asks for force before manually confirming successful uploads", async () => {
    apiMock.getCurrentUser.mockResolvedValueOnce({ user: adminUser });
    apiMock.listWaybillUploads.mockResolvedValue({ items: [uploadItem] });

    render(<WaybillUploadsPage />);

    expect(await screen.findByText("Submitted")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Manually submit 784-84063276" }));

    await waitFor(() => {
      expect(window.confirm).toHaveBeenCalledWith(
        "This upload is already submitted. Mark it as manually submitted and bind locally anyway?"
      );
      expect(apiMock.manualSubmitWaybillUpload).toHaveBeenCalledWith("upload-id", true);
    });
  });

  it("does not show manual confirmation to regular users", async () => {
    apiMock.listWaybillUploads.mockResolvedValue({ items: [uploadItem] });

    render(<WaybillUploadsPage />);

    expect(await screen.findByText("784-84063276")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Manually submit 784-84063276" })
    ).not.toBeInTheDocument();
  });

  it("deletes a local upload record", async () => {
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
      await screen.findByText(
        "Local upload and local Waybill binding deleted for 784-84063276"
      )
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
      await screen.findByText("Air Waybill Gross Weight (KG) must be a number")
    ).toBeInTheDocument();
    expect(apiMock.uploadPreAlertFile).not.toHaveBeenCalled();
  });

  it("redirects unauthenticated users to login", async () => {
    apiMock.getCurrentUser.mockRejectedValueOnce(new Error("Request failed with 401"));

    render(<WaybillUploadsPage />);

    await waitFor(() => {
      expect(routerMock.replace).toHaveBeenCalledWith("/login");
    });
  });
});

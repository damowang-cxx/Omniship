import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WaybillDetailPage from "./page";

const routerMock = vi.hoisted(() => ({
  replace: vi.fn()
}));

const apiMock = vi.hoisted(() => ({
  deleteWaybillPodFile: vi.fn(),
  getCurrentUser: vi.fn(),
  getWaybill: vi.fn(),
  getWaybillPodFileDownloadUrl: vi.fn(
    (publicCode: string, fileId: string) =>
      `/backend/v1/waybills/${publicCode}/pod/${fileId}/download`
  ),
  isUnauthorizedError: vi.fn((error: unknown) =>
    error instanceof Error && error.message.includes("401")
  ),
  listWaybillParcels: vi.fn(),
  logout: vi.fn(),
  uploadWaybillPodFile: vi.fn(),
  updateWaybillParcels: vi.fn(),
  updateWaybill: vi.fn()
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  )
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ publicCode: "A7K2P9QX" }),
  useRouter: () => routerMock
}));

vi.mock("@/lib/api", () => apiMock);

const adminUser = {
  id: "admin-id",
  email: "admin@example.com",
  username: "Admin",
  role: "admin",
  status: "active",
  createdAt: "2026-05-11T10:00:00Z",
  updatedAt: "2026-05-11T10:00:00Z"
};

const waybillItem = {
  id: "waybill-id",
  publicCode: "A7K2P9QX",
  uploadId: "upload-id",
  userId: "user-id",
  number: "784-84063276",
  status: "created",
  statusChangedAt: "2026-05-11T10:00:00Z",
  weightKg: "12.500",
  pieces: 8,
  receivedCount: 0,
  receivedTotal: 8,
  inWarehouseCount: 0,
  fycoStatus: "released",
  releasedCount: 0,
  outboundCount: 0,
  noaAt: null,
  collectionAt: null,
  scannedAt: null,
  customsClearanceAt: null,
  outboundAt: null,
  createdAt: "2026-05-11T10:00:00Z",
  updatedAt: "2026-05-11T10:00:00Z",
  podFiles: []
};

const parcelItems = [
  {
    id: "parcel-1",
    parcelUnitNumber: "CP148956844DE",
    status: "created",
    numberOfItems: 14,
    weightKg: "7.460",
    destinationRaw: "ES",
    destinationCode: "ES",
    destinationName: "Spain",
    inbound: false,
    outbound: false,
    specialInstruction: false,
    createdAt: "2026-05-11T10:00:00Z",
    updatedAt: "2026-05-11T10:00:00Z"
  },
  {
    id: "parcel-2",
    parcelUnitNumber: "CG148125160DE",
    status: "released",
    numberOfItems: 13,
    weightKg: "9.310",
    destinationRaw: "意大利",
    destinationCode: "IT",
    destinationName: "Italy",
    inbound: true,
    outbound: true,
    specialInstruction: false,
    createdAt: "2026-05-11T10:00:00Z",
    updatedAt: "2026-05-11T10:00:00Z"
  }
];

describe("WaybillDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getCurrentUser.mockResolvedValue({ user: adminUser });
    apiMock.getWaybill.mockResolvedValue(waybillItem);
    apiMock.listWaybillParcels.mockResolvedValue({ items: parcelItems });
  });

  it("shows the waybill number title", async () => {
    render(<WaybillDetailPage />);

    expect(await screen.findByRole("heading", { name: "784-84063276" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Waybills" })).toHaveAttribute(
      "href",
      "/waybills"
    );
    expect(apiMock.getWaybill).toHaveBeenCalledWith("A7K2P9QX");
    expect(apiMock.listWaybillParcels).toHaveBeenCalledWith("A7K2P9QX");
  });

  it("keeps the waybill detail available when optional parcel loading fails", async () => {
    apiMock.listWaybillParcels.mockRejectedValueOnce(
      new Error("Request failed with 404: Billing distinct field contains no valid values")
    );

    render(<WaybillDetailPage />);

    expect(await screen.findByRole("heading", { name: "784-84063276" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "Waybill loaded without parcel details. Request failed with 404: Billing distinct field contains no valid values"
      )
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Parcels" })).toBeInTheDocument();
  });

  it("shows Details and Parcels sections with parsed parcel columns", async () => {
    render(<WaybillDetailPage />);

    expect(await screen.findByRole("heading", { name: "Details" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Parcels" })).toBeInTheDocument();
    expect(screen.getByText("Parcel Unit Number")).toBeInTheDocument();
    expect(screen.getByText("Number Of Items")).toBeInTheDocument();
    expect(screen.getByText("Destination group")).toBeInTheDocument();
    expect(screen.getByText("CP148956844DE")).toBeInTheDocument();
    expect(screen.getByText("Spain")).toBeInTheDocument();
    expect(screen.getByLabelText("Parcel Status CP148956844DE")).toHaveValue("created");
  });

  it("lets admins edit milestone times", async () => {
    apiMock.updateWaybill.mockResolvedValue({
      ...waybillItem,
      noaAt: "2026-05-11T12:30:00Z"
    });

    render(<WaybillDetailPage />);

    const noaInput = await screen.findByLabelText("NOA Time");
    fireEvent.change(noaInput, { target: { value: "2026-05-11T12:30" } });
    fireEvent.click(screen.getByRole("button", { name: "Save milestone times" }));

    await waitFor(() => {
      expect(apiMock.updateWaybill).toHaveBeenCalledWith(
        "A7K2P9QX",
        expect.objectContaining({
          noaAt: expect.any(String),
          collectionAt: null,
          scannedAt: null,
          customsClearanceAt: null,
          outboundAt: null
        })
      );
    });
    expect(await screen.findByText("Waybill milestone times updated")).toBeInTheDocument();
  });

  it("shows milestone times as read-only for regular users", async () => {
    apiMock.getCurrentUser.mockResolvedValueOnce({
      user: { ...adminUser, role: "user" }
    });
    apiMock.getWaybill.mockResolvedValueOnce({
      ...waybillItem,
      noaAt: "2026-05-11T12:30:00Z"
    });

    render(<WaybillDetailPage />);

    expect(await screen.findByText("NOA")).toBeInTheDocument();
    expect(screen.queryByLabelText("NOA Time")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Save milestone times" })
    ).not.toBeInTheDocument();
    expect(screen.getByText("Read-only milestones")).toBeInTheDocument();
  });

  it("shows parcels as read-only for regular users", async () => {
    apiMock.getCurrentUser.mockResolvedValueOnce({
      user: { ...adminUser, role: "user" }
    });

    render(<WaybillDetailPage />);

    expect(await screen.findByText("CP148956844DE")).toBeInTheDocument();
    expect(screen.getByText("Created")).toBeInTheDocument();
    expect(screen.queryByLabelText("Parcel Status CP148956844DE")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Select parcel CP148956844DE")).not.toBeInTheDocument();
    expect(screen.getAllByLabelText("Inbound crossed")).toHaveLength(1);
    expect(screen.getAllByLabelText("Outbound checked")).toHaveLength(1);
  });

  it("lets admins bulk update selected parcels", async () => {
    apiMock.updateWaybillParcels.mockResolvedValue({
      items: parcelItems.map((parcel) => ({
        ...parcel,
        status: "inbound",
        inbound: true,
        outbound: false,
        specialInstruction: true
      }))
    });

    render(<WaybillDetailPage />);

    fireEvent.click(await screen.findByLabelText("Select parcel CP148956844DE"));
    fireEvent.change(screen.getByLabelText("Bulk parcel status"), {
      target: { value: "inbound" }
    });
    fireEvent.change(screen.getByLabelText("Bulk parcel Inbound"), {
      target: { value: "true" }
    });
    fireEvent.change(screen.getByLabelText("Bulk parcel Outbound"), {
      target: { value: "false" }
    });
    fireEvent.change(screen.getByLabelText("Bulk parcel Special Instruction"), {
      target: { value: "true" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => {
      expect(apiMock.updateWaybillParcels).toHaveBeenCalledWith("A7K2P9QX", {
        parcelIds: ["parcel-1"],
        status: "inbound",
        inbound: true,
        outbound: false,
        specialInstruction: true
      });
    });
    expect(await screen.findByText("1 parcel updated")).toBeInTheDocument();
  });

  it("shows POD downloads without upload controls for regular users", async () => {
    apiMock.getCurrentUser.mockResolvedValueOnce({
      user: { ...adminUser, role: "user" }
    });
    apiMock.getWaybill.mockResolvedValueOnce({
      ...waybillItem,
      podFiles: [
        {
          id: "pod-1",
          originalFilename: "proof-one.png",
          contentType: "image/png",
          sizeBytes: 2048,
          createdAt: "2026-05-11T12:30:00Z"
        }
      ]
    });

    render(<WaybillDetailPage />);

    expect(await screen.findByText("签收证明")).toBeInTheDocument();
    const downloadLink = screen.getByRole("link", { name: "Download File" });
    expect(downloadLink).toHaveAttribute(
      "href",
      "/backend/v1/waybills/A7K2P9QX/pod/pod-1/download"
    );
    expect(screen.queryByLabelText("POD file")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
  });

  it("lets admins upload and delete POD files", async () => {
    const podFile = {
      id: "pod-1",
      originalFilename: "proof-one.jpg",
      contentType: "image/jpeg",
      sizeBytes: 2048,
      createdAt: "2026-05-11T12:30:00Z"
    };
    apiMock.uploadWaybillPodFile.mockResolvedValue({
      ...waybillItem,
      podFiles: [podFile]
    });
    apiMock.deleteWaybillPodFile.mockResolvedValue({
      status: "deleted",
      podFileId: "pod-1"
    });
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<WaybillDetailPage />);

    const input = await screen.findByLabelText("POD file");
    const file = new File(["jpeg proof"], "proof-one.jpg", {
      type: "image/jpeg"
    });
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload POD" }));

    await waitFor(() => {
      expect(apiMock.uploadWaybillPodFile).toHaveBeenCalledWith("A7K2P9QX", file);
    });
    expect(await screen.findByText("proof-one.jpg")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(apiMock.deleteWaybillPodFile).toHaveBeenCalledWith("A7K2P9QX", "pod-1");
    });
    expect(screen.queryByText("proof-one.jpg")).not.toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  it("redirects unauthenticated users to the public page", async () => {
    apiMock.getCurrentUser.mockRejectedValueOnce(new Error("Request failed with 401"));

    render(<WaybillDetailPage />);

    await waitFor(() => {
      expect(routerMock.replace).toHaveBeenCalledWith("/");
    });
  });
});

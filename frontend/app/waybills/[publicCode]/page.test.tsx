import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WaybillDetailPage from "./page";

const routerMock = vi.hoisted(() => ({
  replace: vi.fn()
}));

const apiMock = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  getWaybill: vi.fn(),
  isUnauthorizedError: vi.fn((error: unknown) =>
    error instanceof Error && error.message.includes("401")
  ),
  logout: vi.fn()
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
  releasedCount: 0,
  outboundCount: 0,
  createdAt: "2026-05-11T10:00:00Z",
  updatedAt: "2026-05-11T10:00:00Z"
};

describe("WaybillDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getCurrentUser.mockResolvedValue({ user: adminUser });
    apiMock.getWaybill.mockResolvedValue(waybillItem);
  });

  it("shows the waybill number title", async () => {
    render(<WaybillDetailPage />);

    expect(await screen.findByRole("heading", { name: "784-84063276" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Waybills" })).toHaveAttribute(
      "href",
      "/waybills"
    );
    expect(apiMock.getWaybill).toHaveBeenCalledWith("A7K2P9QX");
  });

  it("redirects unauthenticated users to the public page", async () => {
    apiMock.getCurrentUser.mockRejectedValueOnce(new Error("Request failed with 401"));

    render(<WaybillDetailPage />);

    await waitFor(() => {
      expect(routerMock.replace).toHaveBeenCalledWith("/");
    });
  });
});

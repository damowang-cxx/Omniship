import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AirWaybillsPage from "./page";

const routerMock = vi.hoisted(() => ({
  replace: vi.fn()
}));

const apiMock = vi.hoisted(() => ({
  getAirWaybillScrapeRun: vi.fn(),
  getCurrentUser: vi.fn(),
  getLatestAirWaybills: vi.fn(),
  getScrapeStatus: vi.fn(),
  isUnauthorizedError: vi.fn((error: unknown) =>
    error instanceof Error && error.message.includes("401")
  ),
  logout: vi.fn(),
  triggerAirWaybillFullRefresh: vi.fn(),
  triggerAirWaybillRefresh: vi.fn(),
  triggerAirWaybillScrape: vi.fn()
}));

vi.mock("next/navigation", () => ({
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

const regularUser = {
  ...adminUser,
  id: "user-id",
  email: "user@example.com",
  username: "User",
  role: "user"
};

describe("AirWaybillsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getCurrentUser.mockResolvedValue({ user: adminUser });
    apiMock.getLatestAirWaybills.mockResolvedValue({
      latestRun: {
        runId: "11111111-1111-1111-1111-111111111111",
        status: "success",
        mode: "incremental",
        rowCount: 2,
        finishedAt: "2026-05-11T10:00:08Z"
      },
      items: [
        {
          number: "784-84063276",
          status: "Released",
          weightKgRaw: "12.50",
          receivedRaw: "Yes",
          parcelsRaw: "68",
          inWarehouseRaw: "Yes",
          releasedRaw: "Yes",
          outboundRaw: "No",
          actionsRaw: "View"
        },
        {
          number: "123-456",
          status: "Received",
          weightKgRaw: "3.00",
          receivedRaw: "Yes",
          parcelsRaw: "12",
          inWarehouseRaw: "No",
          releasedRaw: "No",
          outboundRaw: "No",
          actionsRaw: "View"
        }
      ]
    });
    apiMock.getScrapeStatus.mockResolvedValue({
      latestRun: {
        runId: "11111111-1111-1111-1111-111111111111",
        status: "success",
        mode: "incremental",
        rowCount: 2,
        finishedAt: "2026-05-11T10:00:08Z"
      }
    });
    apiMock.triggerAirWaybillRefresh.mockResolvedValue({
      runId: "22222222-2222-2222-2222-222222222222",
      status: "success",
      mode: "incremental",
      rowCount: 2
    });
    apiMock.triggerAirWaybillFullRefresh.mockResolvedValue({
      runId: "33333333-3333-3333-3333-333333333333",
      status: "success",
      mode: "full",
      rowCount: 2
    });
  });

  it("renders admin shell with refresh buttons and users navigation", async () => {
    render(<AirWaybillsPage />);

    expect(await screen.findByRole("heading", { name: "Omniship" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Waybills" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Waybills/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Users/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /立即更新/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /全量更新/ })).toBeInTheDocument();
    await screen.findByText("784-84063276");
  });

  it("hides admin-only controls for regular users", async () => {
    apiMock.getCurrentUser.mockResolvedValueOnce({ user: regularUser });

    render(<AirWaybillsPage />);

    expect(await screen.findByText("784-84063276")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /立即更新/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /全量更新/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Users/i })).not.toBeInTheDocument();
    expect(apiMock.getScrapeStatus).not.toHaveBeenCalled();
  });

  it("triggers incremental refresh from admin workbench button", async () => {
    render(<AirWaybillsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /立即更新/ }));

    await waitFor(() => {
      expect(apiMock.triggerAirWaybillRefresh).toHaveBeenCalledTimes(1);
    });
  });

  it("triggers full refresh after confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValueOnce(true);
    render(<AirWaybillsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /全量更新/ }));

    await waitFor(() => {
      expect(apiMock.triggerAirWaybillFullRefresh).toHaveBeenCalledTimes(1);
    });
  });

  it("filters number search without hyphen", async () => {
    render(<AirWaybillsPage />);

    fireEvent.change(await screen.findByLabelText("搜索 Number"), {
      target: { value: "78484063276" }
    });

    expect(screen.getByText("784-84063276")).toBeInTheDocument();
    expect(screen.queryByText("123-456")).not.toBeInTheDocument();
  });

  it("limits displayed waybills to the selected page size", async () => {
    apiMock.getLatestAirWaybills.mockResolvedValueOnce({
      latestRun: {
        runId: "11111111-1111-1111-1111-111111111111",
        status: "success",
        mode: "incremental",
        rowCount: 26,
        finishedAt: "2026-05-11T10:00:08Z"
      },
      items: Array.from({ length: 26 }, (_, index) => ({
        number: `WB-${String(index + 1).padStart(2, "0")}`,
        status: "Received",
        weightKgRaw: `${index + 1}`,
        receivedRaw: "Yes",
        parcelsRaw: `${index + 1}`,
        inWarehouseRaw: "No",
        releasedRaw: "No",
        outboundRaw: "No",
        actionsRaw: "View"
      }))
    });

    render(<AirWaybillsPage />);

    expect(await screen.findByText("WB-01")).toBeInTheDocument();
    expect(screen.getByText("WB-25")).toBeInTheDocument();
    expect(screen.queryByText("WB-26")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    expect(await screen.findByText("WB-26")).toBeInTheDocument();
    expect(screen.queryByText("WB-01")).not.toBeInTheDocument();
  });

  it("redirects unauthenticated users to the public landing page", async () => {
    apiMock.getCurrentUser.mockRejectedValueOnce(new Error("Request failed with 401"));

    render(<AirWaybillsPage />);

    await waitFor(() => {
      expect(routerMock.replace).toHaveBeenCalledWith("/");
    });
  });
});

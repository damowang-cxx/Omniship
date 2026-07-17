import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WaybillsPage from "./page";
import {
  WAYBILL_REFRESH_INTERVAL_MS,
  writeAccountCache,
  writeWaybillCache
} from "@/lib/client-cache";
import type { AppUser, WaybillItem } from "@/lib/types";

const routerMock = vi.hoisted(() => ({
  replace: vi.fn()
}));

const apiMock = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  isUnauthorizedError: vi.fn((error: unknown) =>
    error instanceof Error && error.message.includes("401")
  ),
  listUsers: vi.fn(),
  listWaybills: vi.fn(),
  logout: vi.fn(),
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
  useRouter: () => routerMock
}));

vi.mock("@/lib/api", () => apiMock);

const regularUser: AppUser = {
  id: "user-id",
  email: "user@example.com",
  username: "User",
  role: "user",
  status: "active",
  balance: "0.00",
  createdAt: "2026-05-11T10:00:00Z",
  updatedAt: "2026-05-11T10:00:00Z"
};

const adminUser: AppUser = {
  ...regularUser,
  id: "admin-id",
  email: "admin@example.com",
  username: "Admin",
  role: "admin"
};

const waybillItem: WaybillItem = {
  id: "waybill-id",
  publicCode: "A7K2P9QX",
  uploadId: "upload-id",
  userId: "user-id",
  number: "784-84063276",
  status: "noa_received",
  airportOfDeparture: "HKG",
  airportOfArrival: "AMS",
  statusChangedAt: new Date(Date.now() - 8 * 60 * 60 * 1000).toISOString(),
  weightKg: "12.500",
  pieces: 8,
  customsCartons: 5,
  customsAmount: "15.00",
  receivedCount: 0,
  receivedTotal: 8,
  inWarehouseCount: 0,
  palletCount: 2,
  fycoStatus: "released",
  releasedCount: 0,
  outboundCount: 0,
  createdAt: "2026-05-11T10:00:00Z",
  updatedAt: "2026-05-11T10:00:00Z",
  podFiles: [],
  user: {
    id: "user-id",
    email: "user@example.com",
    username: "User"
  }
};

describe("WaybillsPage", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.clearAllMocks();
    apiMock.getCurrentUser.mockResolvedValue({ user: adminUser });
    apiMock.listUsers.mockResolvedValue({ items: [adminUser, regularUser] });
    apiMock.listWaybills.mockResolvedValue({ items: [waybillItem] });
    apiMock.updateWaybill.mockResolvedValue({
      ...waybillItem,
      status: "inbound",
      receivedCount: 5,
      inWarehouseCount: 5,
      palletCount: 4,
      fycoStatus: null,
      releasedCount: 2,
      outboundCount: 1
    });
  });

  it("renders a fresh cached list immediately without refetching waybills", async () => {
    writeAccountCache(adminUser);
    writeWaybillCache(adminUser, {}, [waybillItem]);

    render(<WaybillsPage />);

    expect(screen.queryByText("Loading account information...")).not.toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "784-84063276" })).toBeInTheDocument();
    await waitFor(() => expect(apiMock.getCurrentUser).toHaveBeenCalledTimes(1));
    expect(apiMock.listWaybills).not.toHaveBeenCalled();
  });

  it("shows a container skeleton when the account is ready but waybills are not", async () => {
    let resolveWaybills: ((value: { items: Array<typeof waybillItem> }) => void) | undefined;
    apiMock.listWaybills.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveWaybills = resolve;
      })
    );

    render(<WaybillsPage />);

    expect(await screen.findByRole("heading", { name: "Waybills" })).toBeInTheDocument();
    expect(screen.getByLabelText("Loading waybills")).toBeInTheDocument();
    resolveWaybills?.({ items: [waybillItem] });
    expect(await screen.findByRole("link", { name: "784-84063276" })).toBeInTheDocument();
  });

  it("keeps stale cached rows visible while refreshing them in the background", async () => {
    let resolveWaybills: ((value: { items: WaybillItem[] }) => void) | undefined;
    writeAccountCache(adminUser);
    writeWaybillCache(
      adminUser,
      {},
      [waybillItem],
      Date.now() - WAYBILL_REFRESH_INTERVAL_MS - 1
    );
    apiMock.listWaybills.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveWaybills = resolve;
      })
    );

    render(<WaybillsPage />);

    expect(await screen.findByRole("link", { name: "784-84063276" })).toBeInTheDocument();
    expect(screen.getByText("AMS")).toBeInTheDocument();
    expect(screen.getByText("Updating")).toBeInTheDocument();
    resolveWaybills?.({
      items: [{ ...waybillItem, airportOfArrival: "CDG" }]
    });
    expect(await screen.findByText("CDG")).toBeInTheDocument();
    expect(screen.queryByText("Updating")).not.toBeInTheDocument();
  });

  it("retains cached rows and reports a non-blocking error when refresh fails", async () => {
    writeAccountCache(adminUser);
    writeWaybillCache(
      adminUser,
      {},
      [waybillItem],
      Date.now() - WAYBILL_REFRESH_INTERVAL_MS - 1
    );
    apiMock.listWaybills.mockRejectedValueOnce(new Error("Network unavailable"));

    render(<WaybillsPage />);

    expect(await screen.findByRole("link", { name: "784-84063276" })).toBeInTheDocument();
    expect(await screen.findByText("Showing cached waybills. Network unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Waybills could not be loaded")).not.toBeInTheDocument();
  });

  it("renders approved waybills without an Actions column", async () => {
    render(<WaybillsPage />);

    expect(await screen.findByRole("heading", { name: "Waybills" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "784-84063276" })).toHaveAttribute(
      "href",
      "/waybills/A7K2P9QX"
    );
    expect(screen.getAllByText("NOA Received").length).toBeGreaterThan(0);
    expect(screen.getByText("HKG")).toBeInTheDocument();
    expect(screen.getByText("AMS")).toBeInTheDocument();
    expect(screen.getByText("12.500")).toBeInTheDocument();
    expect(screen.getByText("0 / 8")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Pallet Count" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Cartons" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Customs" })).toBeInTheDocument();
    const waybillRow = screen.getByRole("link", { name: "784-84063276" }).closest("tr");
    expect(waybillRow).not.toBeNull();
    const cells = within(waybillRow as HTMLTableRowElement).getAllByRole("cell");
    expect(cells[7]).toHaveTextContent("5");
    expect(cells[8]).toHaveTextContent("8");
    expect(screen.getByText("€15.00")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Clearance Status" })).toBeInTheDocument();
    expect(screen.getAllByText("Released").length).toBeGreaterThan(0);
    expect(screen.getAllByText("0.00% (0)").length).toBeGreaterThan(0);
    expect(screen.queryByRole("columnheader", { name: "Actions" })).not.toBeInTheDocument();
  });

  it("lets admins filter and edit waybill tracking fields", async () => {
    render(<WaybillsPage />);

    expect(await screen.findByLabelText("Filter User")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Filter User"), {
      target: { value: "user-id" }
    });
    fireEvent.change(screen.getByLabelText("Filter Status"), {
      target: { value: "noa_received" }
    });
    fireEvent.change(screen.getByLabelText("Filter Number"), {
      target: { value: "78484063276" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => {
      expect(apiMock.listWaybills).toHaveBeenLastCalledWith({
        userId: "user-id",
        status: "noa_received",
        q: "78484063276"
      });
    });

    fireEvent.click(screen.getByRole("button", { name: "Edit status 784-84063276" }));
    expect(screen.getAllByRole("option", { name: "Cleared" }).length).toBeGreaterThan(
      1
    );
    fireEvent.change(screen.getByLabelText("Waybill Status"), {
      target: { value: "cleared" }
    });
    fireEvent.change(screen.getByLabelText("Edit Airport of Departure"), {
      target: { value: "fra" }
    });
    fireEvent.change(screen.getByLabelText("Edit Airport of Arrival"), {
      target: { value: "cdg" }
    });
    fireEvent.change(screen.getByLabelText("Received Count"), {
      target: { value: "5" }
    });
    fireEvent.change(screen.getByLabelText("In Warehouse Count"), {
      target: { value: "5" }
    });
    fireEvent.change(screen.getByLabelText("Pallet Count"), {
      target: { value: "4" }
    });
    fireEvent.change(screen.getByLabelText("Clearance Status"), {
      target: { value: "" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(apiMock.updateWaybill).toHaveBeenCalledWith("A7K2P9QX", {
        status: "cleared",
        airportOfDeparture: "FRA",
        airportOfArrival: "CDG",
        receivedCount: 5,
        receivedTotal: 8,
        inWarehouseCount: 5,
        palletCount: 4,
        fycoStatus: null,
        releasedCount: 0,
        outboundCount: 0
      });
    });
  });

  it("hides admin-only controls for regular users", async () => {
    apiMock.getCurrentUser.mockResolvedValueOnce({ user: regularUser });

    render(<WaybillsPage />);

    expect((await screen.findAllByText("NOA Received")).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText("Filter User")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Edit status 784-84063276" })
    ).not.toBeInTheDocument();
    expect(screen.getByText("Uploads")).toBeInTheDocument();
    expect(screen.getAllByText("Waybills").length).toBeGreaterThan(0);
  });

  it("redirects unauthenticated users to the public page", async () => {
    apiMock.getCurrentUser.mockRejectedValueOnce(new Error("Request failed with 401"));

    render(<WaybillsPage />);

    await waitFor(() => {
      expect(routerMock.replace).toHaveBeenCalledWith("/");
    });
  });
});

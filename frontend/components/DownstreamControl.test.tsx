import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DownstreamControl } from "./DownstreamControl";

const api = vi.hoisted(() => ({
  assignDownstream: vi.fn(), getDownstreamDetail: vi.fn(), listDownstreamProviders: vi.fn(), setDownstreamLocks: vi.fn()
}));
vi.mock("@/lib/api", () => api);

describe("DownstreamControl", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listDownstreamProviders.mockResolvedValue([{ code: "AJ", name: "AJ" }]);
    api.getDownstreamDetail.mockResolvedValue({
      publicCode: "TEST0001", providerCode: "AJ", statusLocked: false,
      milestoneLocks: ["customs_clearance_at"], dataLocks: ["outbound_count"],
      lastCheckedAt: null, lastSuccessAt: null, remoteStage: "AWAITING_HANDOVER", remoteCompletion: "IN_TRANSIT",
      snapshot: {}, lastError: null,
      syncReport: {
        quantity_check: { state: "warning", detail: "AJ 顶层 packages 为 1，渠道件数合计为 98，本地提单件数为 98；本轮按渠道数量同步" },
        airline_arrived_at: { state: "synced", value: "2026-11-17T09:24:00+00:00" },
        received_count: { state: "unavailable", detail: "等待 AJ 数量或包裹明细数据" },
        pod_files: { state: "error", detail: "POD download failed" }
      }
    });
    api.setDownstreamLocks.mockImplementation(async (_code, payload) => ({
      ...(await api.getDownstreamDetail()), ...payload
    }));
  });

  it("shows per-field sync results and preserves other locks when toggling one field", async () => {
    render(<DownstreamControl publicCode="TEST0001" awb="TEST-AWB" onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "未归属" }));
    expect(await screen.findByText("航司到达时间")).toBeInTheDocument();
    expect(screen.getByText("暂无来源数据")).toBeInTheDocument();
    expect(screen.getByText("POD download failed")).toBeInTheDocument();
    expect(screen.getByText("数量口径核对")).toBeInTheDocument();
    expect(screen.getByText("数量差异提示")).toHaveAttribute("data-state", "warning");
    expect(screen.getByText(/AJ 顶层 packages 为 1/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("各字段人工锁定设置"));
    fireEvent.click(screen.getByLabelText("人工锁定入库数量"));
    await waitFor(() => expect(api.setDownstreamLocks).toHaveBeenCalledWith("TEST0001", {
      dataLocks: ["outbound_count", "in_warehouse_count"]
    }));
    await waitFor(() => expect(screen.getByLabelText("人工锁定入库数量")).toBeEnabled());
    fireEvent.click(screen.getByLabelText("人工锁定NOA 时间"));
    await waitFor(() => expect(api.setDownstreamLocks).toHaveBeenLastCalledWith("TEST0001", {
      milestoneLocks: ["customs_clearance_at", "noa_at"]
    }));
  });
});

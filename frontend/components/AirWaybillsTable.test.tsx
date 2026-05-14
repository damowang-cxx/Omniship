import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AirWaybillsTable } from "./AirWaybillsTable";

describe("AirWaybillsTable", () => {
  it("renders empty state", () => {
    render(<AirWaybillsTable items={[]} />);
    expect(screen.getByText("暂无最新成功抓取数据")).toBeInTheDocument();
  });

  it("renders row fields in expected columns", () => {
    render(
      <AirWaybillsTable
        items={[
          {
            number: "123456",
            status: "Released",
            weightKgRaw: "12.50",
            receivedRaw: "Yes",
            parcelsRaw: "68",
            inWarehouseRaw: "Yes",
            releasedRaw: "Yes",
            outboundRaw: "No",
            actionsRaw: "View"
          }
        ]}
      />
    );

    expect(screen.getByText("Number")).toBeInTheDocument();
    expect(screen.getByText("Parcels")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "123456" })).toHaveAttribute(
      "href",
      "/air-waybills/123456"
    );
    expect(screen.getAllByText("Released")).toHaveLength(2);
    expect(screen.queryByText("Actions")).not.toBeInTheDocument();
    expect(screen.queryByText("View")).not.toBeInTheDocument();
  });

  it("renders sortable headers when sorting props are provided", () => {
    render(
      <AirWaybillsTable
        items={[
          {
            number: "123456",
            parcelsRaw: "68"
          }
        ]}
        onSort={() => undefined}
        sortState={null}
      />
    );

    expect(screen.getByRole("button", { name: "Number 升序排序" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Parcels 升序排序" })).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScrapeStatusCard } from "./ScrapeStatusCard";

describe("ScrapeStatusCard", () => {
  it("renders default status when no run exists", () => {
    render(<ScrapeStatusCard latestRun={null} />);

    expect(screen.getByText("未抓取")).toBeInTheDocument();
    expect(screen.getByText("抓取行数")).toBeInTheDocument();
  });

  it("renders success run status", () => {
    render(
      <ScrapeStatusCard
        latestRun={{
          runId: "11111111-1111-1111-1111-111111111111",
          status: "success",
          rowCount: 2,
          finishedAt: "2026-05-11T10:00:08Z"
        }}
      />
    );

    expect(screen.getByText("成功")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });
});


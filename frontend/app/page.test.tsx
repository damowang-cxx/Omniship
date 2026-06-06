import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LandingPage from "./page";

const routerMock = vi.hoisted(() => ({
  replace: vi.fn()
}));

const apiMock = vi.hoisted(() => ({
  getCurrentUser: vi.fn()
}));

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock
}));

vi.mock("@/lib/api", () => apiMock);

describe("LandingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getCurrentUser.mockRejectedValue(new Error("Request failed with 401"));
  });

  it("shows the public EPIX air freight landing page", async () => {
    render(<LandingPage />);

    expect(screen.getByRole("link", { name: "EPIX home" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "EPIX keeps urgent air cargo moving with clarity."
      })
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Login" })).toHaveAttribute(
      "href",
      "/login"
    );
    expect(screen.getByText("Priority air freight")).toBeInTheDocument();
    expect(screen.getByText("contact@example.com")).toBeInTheDocument();

    await waitFor(() => {
      expect(routerMock.replace).not.toHaveBeenCalled();
    });
  });

  it("redirects logged-in users to waybills", async () => {
    apiMock.getCurrentUser.mockResolvedValueOnce({
      user: {
        id: "admin-id",
        email: "admin@example.com",
        username: "Admin",
        role: "admin",
        status: "active"
      }
    });

    render(<LandingPage />);

    await waitFor(() => {
      expect(routerMock.replace).toHaveBeenCalledWith("/waybills");
    });
  });
});

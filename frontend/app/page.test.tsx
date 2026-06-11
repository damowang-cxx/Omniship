import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LandingPage from "./page";
import LandingPageClient from "./LandingPageClient";

const routerMock = vi.hoisted(() => ({
  replace: vi.fn()
}));

const apiMock = vi.hoisted(() => ({
  getCurrentUser: vi.fn()
}));

const requestMock = vi.hoisted(() => ({
  cookies: {
    get: vi.fn()
  },
  headers: {
    get: vi.fn()
  }
}));

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock
}));

vi.mock("@/lib/api", () => apiMock);

vi.mock("next/headers", () => ({
  cookies: () => requestMock.cookies,
  headers: () => requestMock.headers
}));

describe("LandingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getCurrentUser.mockRejectedValue(new Error("Request failed with 401"));
    requestMock.cookies.get.mockReturnValue(undefined);
    requestMock.headers.get.mockReturnValue(null);
    document.cookie = "epix_locale=; path=/; max-age=0";
    document.documentElement.lang = "en";
  });

  it("shows the public EPIX air freight landing page", async () => {
    render(<LandingPage />);

    expect(screen.getByRole("link", { name: "EPIX home" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "HOME" })).toHaveAttribute(
      "href",
      "#home"
    );
    expect(screen.getByRole("link", { name: "SERVICE" })).toHaveAttribute(
      "href",
      "#services"
    );
    expect(screen.getByRole("link", { name: "WHY EPIX" })).toHaveAttribute(
      "href",
      "#why-epix"
    );
    expect(screen.getByRole("link", { name: "CONTACT" })).toHaveAttribute(
      "href",
      "#contact"
    );
    expect(screen.queryByRole("link", { name: "Process" })).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "EPIX, Your Trusted Partner for E-commerce Logistics."
      })
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Login" })).toHaveAttribute(
      "href",
      "/login"
    );
    expect(screen.getByText("Fast Air Freight Solutions")).toBeInTheDocument();
    expect(screen.getByText("European Customs Expertise")).toBeInTheDocument();
    expect(screen.getByText("Dedicated Customer Support")).toBeInTheDocument();
    expect(screen.getByText("Extensive European Network")).toBeInTheDocument();
    expect(screen.getByText("hello@epix-logistics.com")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Logistics partners" })
    ).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Colissimo" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "FedEx" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "DHL" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "DPD" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "UPS" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Peddler" })).toBeInTheDocument();

    await waitFor(() => {
      expect(routerMock.replace).not.toHaveBeenCalled();
    });
  });

  it("renders Chinese copy from the detected request locale", () => {
    requestMock.headers.get.mockReturnValue("zh");

    render(<LandingPage />);

    expect(
      screen.getByRole("heading", {
        name: "EPIX，您值得信赖的电商物流合作伙伴。"
      })
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "登录" })).toHaveAttribute(
      "href",
      "/login"
    );
    expect(screen.getByRole("link", { name: "首页" })).toHaveAttribute(
      "href",
      "#home"
    );
    expect(screen.getByRole("link", { name: "服务" })).toHaveAttribute(
      "href",
      "#services"
    );
    expect(screen.getByRole("link", { name: "为什么选择 EPIX" })).toHaveAttribute(
      "href",
      "#why-epix"
    );
    expect(screen.getByRole("link", { name: "联系" })).toHaveAttribute(
      "href",
      "#contact"
    );
    expect(screen.getByText("快速空运解决方案")).toBeInTheDocument();
    expect(screen.getByText("欧洲清关专业能力")).toBeInTheDocument();
    expect(screen.getByText("广泛的欧洲网络")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "合作伙伴" })).toBeInTheDocument();
  });

  it("lets visitors switch the landing page language", () => {
    render(<LandingPageClient initialLocale="en" />);

    fireEvent.click(screen.getByRole("button", { name: "Change language" }));
    fireEvent.click(screen.getByRole("menuitemradio", { name: /中文/ }));

    expect(
      screen.getByRole("heading", {
        name: "EPIX，您值得信赖的电商物流合作伙伴。"
      })
    ).toBeInTheDocument();
    expect(document.cookie).toContain("epix_locale=zh");
    expect(document.documentElement.lang).toBe("zh-CN");
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

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LoginPage from "./page";

const routerMock = vi.hoisted(() => ({
  replace: vi.fn()
}));

const apiMock = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  login: vi.fn()
}));

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock
}));

vi.mock("@/lib/api", () => apiMock);

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getCurrentUser.mockRejectedValue(new Error("Request failed with 401"));
    apiMock.login.mockResolvedValue({ user: { email: "admin@example.com" } });
  });

  it("submits credentials and redirects to Waybills", async () => {
    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText("邮箱"), {
      target: { value: "admin@example.com" }
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "password123" }
    });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(apiMock.login).toHaveBeenCalledWith("admin@example.com", "password123");
      expect(routerMock.replace).toHaveBeenCalledWith("/air-waybills");
    });
  });

  it("shows an error when login fails", async () => {
    apiMock.login.mockRejectedValueOnce(new Error("Request failed with 401"));

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText("邮箱"), {
      target: { value: "admin@example.com" }
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "badpassword" }
    });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByText("邮箱或密码不正确，或账号已被禁用。")).toBeInTheDocument();
  });
});

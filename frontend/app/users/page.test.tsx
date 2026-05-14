import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import UsersPage from "./page";

const routerMock = vi.hoisted(() => ({
  replace: vi.fn()
}));

const apiMock = vi.hoisted(() => ({
  createUser: vi.fn(),
  getCurrentUser: vi.fn(),
  isUnauthorizedError: vi.fn((error: unknown) =>
    error instanceof Error && error.message.includes("401")
  ),
  listUsers: vi.fn(),
  logout: vi.fn(),
  resetUserPassword: vi.fn(),
  updateUserStatus: vi.fn()
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

describe("UsersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getCurrentUser.mockResolvedValue({ user: adminUser });
    apiMock.listUsers.mockResolvedValue({
      items: [
        adminUser,
        {
          id: "user-id",
          email: "operator@example.com",
          username: "Operator",
          role: "user",
          status: "active",
          createdAt: "2026-05-11T10:00:00Z",
          updatedAt: "2026-05-11T10:00:00Z"
        }
      ]
    });
    apiMock.createUser.mockResolvedValue({ id: "new-user" });
    apiMock.updateUserStatus.mockResolvedValue({ id: "user-id" });
    apiMock.resetUserPassword.mockResolvedValue({ id: "user-id" });
  });

  it("renders users navigation and list for admin", async () => {
    render(<UsersPage />);

    expect(await screen.findByRole("heading", { name: "Users" })).toBeInTheDocument();
    expect(screen.getByText("operator@example.com")).toBeInTheDocument();
  });

  it("creates a regular user", async () => {
    render(<UsersPage />);

    fireEvent.change(await screen.findByLabelText("邮箱"), {
      target: { value: "new@example.com" }
    });
    fireEvent.change(screen.getByLabelText("用户名"), {
      target: { value: "New User" }
    });
    fireEvent.change(screen.getByLabelText("初始密码"), {
      target: { value: "password123" }
    });
    fireEvent.click(screen.getByRole("button", { name: "创建用户" }));

    await waitFor(() => {
      expect(apiMock.createUser).toHaveBeenCalledWith({
        email: "new@example.com",
        username: "New User",
        password: "password123"
      });
    });
  });
});

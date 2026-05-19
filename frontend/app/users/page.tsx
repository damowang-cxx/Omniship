"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { AppMessage } from "@/components/InfoCenter";
import {
  createUser,
  getCurrentUser,
  isUnauthorizedError,
  listUsers,
  logout,
  resetUserPassword,
  updateUserStatus
} from "@/lib/api";
import type { AppUser } from "@/lib/types";
import styles from "./page.module.css";

export default function UsersPage() {
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<AppUser | null>(null);
  const [users, setUsers] = useState<AppUser[]>([]);
  const [authError, setAuthError] = useState<string | null>(null);
  const [messages, setMessages] = useState<AppMessage[]>([]);
  const [isInfoOpen, setIsInfoOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [resetTarget, setResetTarget] = useState<AppUser | null>(null);
  const [resetPassword, setResetPassword] = useState("");

  const addMessage = useCallback((title: string, body: string) => {
    setMessages((current) => [
      {
        id: `${Date.now()}-${current.length}`,
        title,
        body,
        tone: "error",
        createdAt: new Date().toISOString(),
        read: false
      },
      ...current
    ]);
  }, []);

  const refreshUsers = useCallback(async () => {
    try {
      const response = await listUsers();
      setUsers(response.items);
    } catch (error) {
      if (isUnauthorizedError(error)) {
        router.replace("/");
        return;
      }
      addMessage("用户列表加载失败", error instanceof Error ? error.message : "请求失败");
    }
  }, [addMessage, router]);

  useEffect(() => {
    async function bootstrap() {
      try {
        const response = await getCurrentUser();
        setCurrentUser(response.user);
        if (response.user.role === "admin") {
          await refreshUsers();
        }
      } catch (error) {
        setAuthError(
          error instanceof Error ? error.message : "无法加载账号信息"
        );
        router.replace("/");
      } finally {
        setIsLoading(false);
      }
    }

    void bootstrap();
  }, [refreshUsers, router]);

  async function handleCreateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await createUser({ email, username, password });
      setEmail("");
      setUsername("");
      setPassword("");
      await refreshUsers();
    } catch (error) {
      addMessage("创建用户失败", error instanceof Error ? error.message : "请求失败");
    }
  }

  async function handleToggleStatus(user: AppUser) {
    const nextStatus = user.status === "active" ? "disabled" : "active";
    try {
      await updateUserStatus(user.id, nextStatus);
      await refreshUsers();
    } catch (error) {
      addMessage("更新用户状态失败", error instanceof Error ? error.message : "请求失败");
    }
  }

  async function handleResetPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resetTarget) {
      return;
    }
    try {
      await resetUserPassword(resetTarget.id, resetPassword);
      setResetTarget(null);
      setResetPassword("");
      await refreshUsers();
    } catch (error) {
      addMessage("重置密码失败", error instanceof Error ? error.message : "请求失败");
    }
  }

  const unreadCount = messages.filter((message) => !message.read).length;

  if (isLoading) {
    return <main className={styles.loadingPage}>正在加载账号信息...</main>;
  }

  if (authError || !currentUser) {
    return (
      <main className={styles.loadingPage}>
        <p>Account session unavailable. Redirecting to the public EPIX page...</p>
        <button onClick={() => router.replace("/")} type="button">
          Return home
        </button>
      </main>
    );
  }

  return (
    <AppShell
      active="users"
      isInfoOpen={isInfoOpen}
      messages={messages}
      onInfoClose={() => setIsInfoOpen(false)}
      onInfoOpen={() => {
        setIsInfoOpen(true);
        setMessages((current) => current.map((message) => ({ ...message, read: true })));
      }}
      onLogout={async () => {
        await logout();
        router.replace("/");
      }}
      unreadCount={unreadCount}
      user={currentUser}
    >
      <section className={styles.workspace}>
        <div className={styles.header}>
          <div>
            <p>Admin</p>
            <h2>Users</h2>
          </div>
        </div>

        {currentUser.role !== "admin" ? (
          <div className={styles.forbidden}>403 无权限访问用户管理。</div>
        ) : (
          <>
            <form className={styles.form} onSubmit={handleCreateUser}>
              <h3>创建普通账号</h3>
              <input
                aria-label="邮箱"
                onChange={(event) => setEmail(event.target.value)}
                placeholder="邮箱"
                required
                type="email"
                value={email}
              />
              <input
                aria-label="用户名"
                onChange={(event) => setUsername(event.target.value)}
                placeholder="用户名"
                required
                value={username}
              />
              <input
                aria-label="初始密码"
                minLength={8}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="初始密码"
                required
                type="password"
                value={password}
              />
              <button type="submit">创建用户</button>
            </form>

            {resetTarget && (
              <form className={styles.resetPanel} onSubmit={handleResetPassword}>
                <strong>重置 {resetTarget.email} 的密码</strong>
                <input
                  aria-label="新密码"
                  minLength={8}
                  onChange={(event) => setResetPassword(event.target.value)}
                  placeholder="新密码"
                  required
                  type="password"
                  value={resetPassword}
                />
                <button type="submit">确认重置</button>
                <button onClick={() => setResetTarget(null)} type="button">
                  取消
                </button>
              </form>
            )}

            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>邮箱</th>
                    <th>用户名</th>
                    <th>角色</th>
                    <th>状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td>{user.email}</td>
                      <td>{user.username}</td>
                      <td>{user.role === "admin" ? "管理员" : "普通用户"}</td>
                      <td>{user.status === "active" ? "启用" : "禁用"}</td>
                      <td>
                        <div className={styles.actions}>
                          <button onClick={() => handleToggleStatus(user)} type="button">
                            {user.status === "active" ? "禁用" : "启用"}
                          </button>
                          <button onClick={() => setResetTarget(user)} type="button">
                            重置密码
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </AppShell>
  );
}

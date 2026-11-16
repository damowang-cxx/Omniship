"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArchiveX, ClipboardList, Factory, FileText, LogOut, Package, UploadCloud, Users, WalletCards } from "lucide-react";
import type { AppUser } from "@/lib/types";
import type { DownstreamIncident } from "@/lib/types";
import { listDownstreamIncidents, markDownstreamIncidentsRead } from "@/lib/api";
import { AppMessage, InfoCenter } from "./InfoCenter";
import styles from "./AppShell.module.css";

export function AppShell({
  user,
  active,
  messages,
  unreadCount,
  isInfoOpen,
  onInfoOpen,
  onInfoClose,
  onLogout,
  children
}: {
  user: AppUser;
  active: "waybills" | "uploads" | "upload-management" | "cancelled-waybills" | "users" | "billing" | "suppliers" | "invoice-settings";
  messages: AppMessage[];
  unreadCount: number;
  isInfoOpen: boolean;
  onInfoOpen: () => void;
  onInfoClose: () => void;
  onLogout: () => void;
  children: React.ReactNode;
}) {
  const isAdmin = user.role === "admin";
  const [incidents, setIncidents] = useState<DownstreamIncident[]>([]);
  const refreshIncidents = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const result = await listDownstreamIncidents();
      setIncidents(Array.isArray(result) ? result : []);
    } catch {
      // Local notices remain usable during a temporary API failure.
    }
  }, [isAdmin]);

  useEffect(() => {
    if (!isAdmin) return;
    void refreshIncidents();
    const timer = window.setInterval(() => void refreshIncidents(), 60_000);
    return () => window.clearInterval(timer);
  }, [isAdmin, refreshIncidents]);

  const incidentMessages = useMemo<AppMessage[]>(() => incidents.map((incident) => ({
    id: incident.id,
    title: incident.resolvedAt ? `${incident.providerCode} 同步异常已恢复` : `${incident.providerCode} 同步异常`,
    body: `提单号：${incident.awb}；时间：${new Intl.DateTimeFormat("zh-CN", { dateStyle: "short", timeStyle: "medium", timeZone: "Asia/Shanghai" }).format(new Date(incident.openedAt))}；具体错误：${incident.detail}${incident.resolvedAt ? `；恢复时间：${new Intl.DateTimeFormat("zh-CN", { dateStyle: "short", timeStyle: "medium", timeZone: "Asia/Shanghai" }).format(new Date(incident.resolvedAt))}` : ""}`,
    createdAt: incident.openedAt,
    tone: incident.resolvedAt ? "info" : "error",
    read: incident.read
  })), [incidents]);

  const openInfo = useCallback(() => {
    onInfoOpen();
    const unreadIds = incidents.filter((item) => !item.read).map((item) => item.id);
    if (unreadIds.length) {
      setIncidents((current) => current.map((item) => ({ ...item, read: true })));
      void (async () => {
        try { await markDownstreamIncidentsRead(unreadIds); } catch { await refreshIncidents(); }
      })();
    }
  }, [incidents, onInfoOpen, refreshIncidents]);

  return (
    <div className={styles.shell}>
      <header className={styles.topbar}>
        <h1>EPIX</h1>
        <div className={styles.topActions}>
          {isAdmin && (
            <InfoCenter
              isOpen={isInfoOpen}
              onClose={onInfoClose}
              onOpen={openInfo}
              unreadCount={unreadCount + incidents.filter((item) => !item.read).length}
              messages={[...incidentMessages, ...messages]}
            />
          )}
          <button className={styles.logoutButton} onClick={onLogout} type="button">
            <LogOut aria-hidden="true" size={18} />
            Logout
          </button>
        </div>
      </header>

      <div className={styles.body}>
        <aside className={styles.sidebar}>
          <div className={styles.userCard}>
            <div className={styles.avatar}>{user.username.slice(0, 2).toUpperCase()}</div>
            <div>
              <span>Account</span>
              <strong>{user.username}</strong>
              <small>{user.email}</small>
              <small>{isAdmin ? "Admin" : "User"}</small>
            </div>
          </div>

          <nav className={styles.nav} aria-label="Primary navigation">
            <p>Navigation</p>
            <Link
              aria-current={active === "waybills" ? "page" : undefined}
              className={styles.navItem}
              data-active={active === "waybills"}
              href="/waybills"
            >
              <Package aria-hidden="true" size={18} />
              <span>Waybills</span>
            </Link>
            <Link
              aria-current={active === "uploads" ? "page" : undefined}
              className={styles.navItem}
              data-active={active === "uploads"}
              href="/waybill-uploads"
            >
              <UploadCloud aria-hidden="true" size={18} />
              <span>Uploads</span>
            </Link>
            {!isAdmin && (
              <Link
                aria-current={active === "billing" ? "page" : undefined}
                className={styles.navItem}
                data-active={active === "billing"}
                href="/billing"
              >
                <WalletCards aria-hidden="true" size={18} />
                <span>Billing</span>
              </Link>
            )}
            {isAdmin && (
              <Link
                aria-current={active === "invoice-settings" ? "page" : undefined}
                className={styles.navItem}
                data-active={active === "invoice-settings"}
                href="/invoice-settings"
              >
                <FileText aria-hidden="true" size={18} />
                <span>Invoice Settings</span>
              </Link>
            )}
            {isAdmin && (
              <Link
                aria-current={active === "suppliers" ? "page" : undefined}
                className={styles.navItem}
                data-active={active === "suppliers"}
                href="/suppliers"
              >
                <Factory aria-hidden="true" size={18} />
                <span>Supplier</span>
              </Link>
            )}
            {isAdmin && (
              <Link
                aria-current={active === "cancelled-waybills" ? "page" : undefined}
                className={styles.navItem}
                data-active={active === "cancelled-waybills"}
                href="/cancelled-waybills"
              >
                <ArchiveX aria-hidden="true" size={18} />
                <span>Cancelled Waybills</span>
              </Link>
            )}
            {isAdmin && (
              <Link
                aria-current={active === "upload-management" ? "page" : undefined}
                className={styles.navItem}
                data-active={active === "upload-management"}
                href="/waybill-upload-management"
              >
                <ClipboardList aria-hidden="true" size={18} />
                <span>Waybill Management</span>
              </Link>
            )}
            {isAdmin && (
              <Link
                aria-current={active === "users" ? "page" : undefined}
                className={styles.navItem}
                data-active={active === "users"}
                href="/users"
              >
                <Users aria-hidden="true" size={18} />
                <span>Users</span>
              </Link>
            )}
          </nav>
        </aside>

        <main className={styles.main}>{children}</main>
      </div>
    </div>
  );
}

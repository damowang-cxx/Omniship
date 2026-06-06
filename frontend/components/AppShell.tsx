import Link from "next/link";
import { ClipboardList, LogOut, UploadCloud, Users } from "lucide-react";
import type { AppUser } from "@/lib/types";
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
  active: "uploads" | "upload-management" | "users";
  messages: AppMessage[];
  unreadCount: number;
  isInfoOpen: boolean;
  onInfoOpen: () => void;
  onInfoClose: () => void;
  onLogout: () => void;
  children: React.ReactNode;
}) {
  const isAdmin = user.role === "admin";

  return (
    <div className={styles.shell}>
      <header className={styles.topbar}>
        <h1>EPIX</h1>
        <div className={styles.topActions}>
          {isAdmin && (
            <InfoCenter
              isOpen={isInfoOpen}
              messages={messages}
              onClose={onInfoClose}
              onOpen={onInfoOpen}
              unreadCount={unreadCount}
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
              aria-current={active === "uploads" ? "page" : undefined}
              className={styles.navItem}
              data-active={active === "uploads"}
              href="/waybill-uploads"
            >
              <UploadCloud aria-hidden="true" size={18} />
              <span>Uploads</span>
            </Link>
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

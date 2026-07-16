"use client";
/* eslint-disable @next/next/no-img-element */

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowDownRight,
  Eye,
  ImageIcon,
  Plus,
  ReceiptText,
  WalletCards,
  X
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { AppMessage } from "@/components/InfoCenter";
import {
  createUser,
  deleteUser,
  getCurrentUser,
  getRechargeReceiptUrl,
  getUserBillingAccount,
  isUnauthorizedError,
  listUsers,
  logout,
  rechargeUser,
  resetUserPassword,
  updateUserStatus
} from "@/lib/api";
import type { AppUser, BillingAccountResponse } from "@/lib/types";
import styles from "./page.module.css";

function formatEuro(value: string | undefined) {
  return new Intl.NumberFormat("en-IE", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2
  }).format(Number(value || 0));
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

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
  const [detailUser, setDetailUser] = useState<AppUser | null>(null);
  const [billing, setBilling] = useState<BillingAccountResponse | null>(null);
  const [billingTab, setBillingTab] = useState<"deductions" | "recharges">("deductions");
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [isRechargeOpen, setIsRechargeOpen] = useState(false);
  const [rechargeAmount, setRechargeAmount] = useState("");
  const [receiptFile, setReceiptFile] = useState<File | null>(null);
  const [isRecharging, setIsRecharging] = useState(false);
  const [receiptPreview, setReceiptPreview] = useState<{ url: string; name: string } | null>(null);

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
      addMessage("Unable to load users", error instanceof Error ? error.message : "Request failed");
    }
  }, [addMessage, router]);

  const loadUserBilling = useCallback(async (user: AppUser) => {
    setDetailUser(user);
    setBilling(null);
    setDetailError(null);
    setIsDetailLoading(true);
    try {
      const account = await getUserBillingAccount(user.id);
      setBilling(account);
      setDetailUser(account.user);
    } catch (error) {
      if (isUnauthorizedError(error)) {
        router.replace("/");
        return;
      }
      setDetailError(error instanceof Error ? error.message : "Unable to load billing details");
    } finally {
      setIsDetailLoading(false);
    }
  }, [router]);

  useEffect(() => {
    async function bootstrap() {
      try {
        const response = await getCurrentUser();
        setCurrentUser(response.user);
        if (response.user.role === "admin") {
          await refreshUsers();
        }
      } catch (error) {
        setAuthError(error instanceof Error ? error.message : "Unable to load account information");
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
      addMessage("Unable to create user", error instanceof Error ? error.message : "Request failed");
    }
  }

  async function handleToggleStatus(user: AppUser) {
    try {
      await updateUserStatus(user.id, user.status === "active" ? "disabled" : "active");
      await refreshUsers();
    } catch (error) {
      addMessage("Unable to update user", error instanceof Error ? error.message : "Request failed");
    }
  }

  async function handleResetPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resetTarget) return;
    try {
      await resetUserPassword(resetTarget.id, resetPassword);
      setResetTarget(null);
      setResetPassword("");
      await refreshUsers();
    } catch (error) {
      addMessage("Unable to reset password", error instanceof Error ? error.message : "Request failed");
    }
  }

  async function handleDeleteUser(user: AppUser) {
    if (user.id === currentUser?.id) {
      addMessage("Cannot delete current account", "Use another administrator account to delete this user.");
      return;
    }
    if (!window.confirm(`Delete user ${user.email}?`)) return;
    try {
      await deleteUser(user.id);
      await refreshUsers();
    } catch (error) {
      addMessage("Unable to delete user", error instanceof Error ? error.message : "Request failed");
    }
  }

  async function handleRecharge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detailUser) return;
    setIsRecharging(true);
    setDetailError(null);
    try {
      const account = await rechargeUser(detailUser.id, rechargeAmount, receiptFile);
      setBilling(account);
      setDetailUser(account.user);
      setBillingTab("recharges");
      setRechargeAmount("");
      setReceiptFile(null);
      setIsRechargeOpen(false);
      await refreshUsers();
    } catch (error) {
      if (isUnauthorizedError(error)) {
        router.replace("/");
        return;
      }
      setDetailError(error instanceof Error ? error.message : "Unable to recharge account");
    } finally {
      setIsRecharging(false);
    }
  }

  const unreadCount = messages.filter((message) => !message.read).length;

  if (isLoading) {
    return <main className={styles.loadingPage}>Loading account information...</main>;
  }

  if (authError || !currentUser) {
    return (
      <main className={styles.loadingPage}>
        <p>Account session unavailable. Redirecting to the public EPIX page...</p>
        <button onClick={() => router.replace("/")} type="button">Return home</button>
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
          <div className={styles.forbidden}>403: You do not have access to user management.</div>
        ) : (
          <>
            <form className={styles.form} onSubmit={handleCreateUser}>
              <h3>Create user account</h3>
              <input aria-label="Email" onChange={(event) => setEmail(event.target.value)} placeholder="Email" required type="email" value={email} />
              <input aria-label="Username" onChange={(event) => setUsername(event.target.value)} placeholder="Username" required value={username} />
              <input aria-label="Initial password" minLength={8} onChange={(event) => setPassword(event.target.value)} placeholder="Initial password" required type="password" value={password} />
              <button type="submit">Create user</button>
            </form>

            {resetTarget && (
              <form className={styles.resetPanel} onSubmit={handleResetPassword}>
                <strong>Reset password for {resetTarget.email}</strong>
                <input aria-label="New password" minLength={8} onChange={(event) => setResetPassword(event.target.value)} placeholder="New password" required type="password" value={resetPassword} />
                <button type="submit">Confirm reset</button>
                <button onClick={() => setResetTarget(null)} type="button">Cancel</button>
              </form>
            )}

            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Username</th>
                    <th>Role</th>
                    <th>Balance</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td>
                        <button className={styles.emailLink} onClick={() => void loadUserBilling(user)} type="button">
                          {user.email}
                        </button>
                      </td>
                      <td>{user.username}</td>
                      <td>{user.role === "admin" ? "Admin" : "User"}</td>
                      <td><span className={styles.balanceCell}>{formatEuro(user.balance)}</span></td>
                      <td><span className={styles.statusPill} data-status={user.status}>{user.status === "active" ? "Active" : "Disabled"}</span></td>
                      <td>
                        <div className={styles.actions}>
                          <button onClick={() => void handleToggleStatus(user)} type="button">{user.status === "active" ? "Disable" : "Enable"}</button>
                          <button onClick={() => setResetTarget(user)} type="button">Reset password</button>
                          <button className={styles.dangerButton} disabled={user.id === currentUser.id} onClick={() => void handleDeleteUser(user)} type="button">Delete</button>
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

      {detailUser && (
        <div className={styles.modalBackdrop} onMouseDown={() => setDetailUser(null)} role="presentation">
          <section aria-labelledby="user-detail-title" aria-modal="true" className={styles.userDetailModal} onMouseDown={(event) => event.stopPropagation()} role="dialog">
            <header className={styles.modalHeader}>
              <div>
                <p>Customer account</p>
                <h3 id="user-detail-title">User details</h3>
              </div>
              <button aria-label="Close user details" className={styles.iconButton} onClick={() => setDetailUser(null)} type="button"><X aria-hidden="true" size={18} /></button>
            </header>

            <div className={styles.userSummary}>
              <div><span>Email</span><strong>{detailUser.email}</strong></div>
              <div><span>Username</span><strong>{detailUser.username}</strong></div>
              <div><span>Role</span><strong>{detailUser.role === "admin" ? "Admin" : "User"}</strong></div>
              <div><span>Status</span><strong>{detailUser.status === "active" ? "Active" : "Disabled"}</strong></div>
              <div className={styles.summaryBalance}><span>Balance</span><strong>{formatEuro(detailUser.balance)}</strong></div>
            </div>

            <div className={styles.billingToolbar}>
              <div className={styles.tabs} role="tablist" aria-label="Customer billing sections">
                <button aria-selected={billingTab === "deductions"} data-active={billingTab === "deductions"} onClick={() => setBillingTab("deductions")} role="tab" type="button">Deduction entries</button>
                <button aria-selected={billingTab === "recharges"} data-active={billingTab === "recharges"} onClick={() => setBillingTab("recharges")} role="tab" type="button">Recharge records</button>
              </div>
              {billingTab === "recharges" && (
                <button className={styles.rechargeButton} onClick={() => setIsRechargeOpen(true)} type="button"><Plus aria-hidden="true" size={16} />Recharge</button>
              )}
            </div>

            {detailError && <div className={styles.modalError} role="alert">{detailError}</div>}
            {isDetailLoading ? (
              <div className={styles.modalEmpty}>Loading customer billing...</div>
            ) : billingTab === "deductions" ? (
              billing?.deductions.length ? (
                <div className={styles.ledgerTableWrap}>
                  <table><thead><tr><th>Air Waybill Number</th><th>Supplier</th><th>Source</th><th>Calculation</th><th>Deducted At</th><th>Amount</th><th>Balance After</th></tr></thead><tbody>
                    {billing.deductions.map((entry) => <tr key={entry.id}><td>{entry.waybillNumber || "-"}</td><td>{entry.supplierName ? `${entry.supplierName} v${entry.supplierVersionNumber}` : "-"}</td><td>{entry.billingSource === "retroactive" ? "Tax backfill" : "Upload"}</td><td>{entry.billableUnitCount != null && entry.unitRate ? `${entry.billableUnitCount} × ${formatEuro(entry.unitRate)}` : "-"}</td><td>{formatDateTime(entry.createdAt)}</td><td><span className={styles.deductionAmount}><ArrowDownRight aria-hidden="true" size={14} />{formatEuro(entry.amount)}</span></td><td>{formatEuro(entry.balanceAfter)}</td></tr>)}
                  </tbody></table>
                </div>
              ) : <div className={styles.modalEmpty}><ReceiptText aria-hidden="true" size={26} /><strong>No deduction entries</strong><span>Posted waybill tax charges will appear here.</span></div>
            ) : billing?.recharges.length ? (
              <div className={styles.ledgerTableWrap}>
                <table><thead><tr><th>Recharge Time</th><th>Amount</th><th>Balance After</th><th>Receipt</th></tr></thead><tbody>
                  {billing.recharges.map((entry) => (
                    <tr key={entry.id}><td>{formatDateTime(entry.createdAt)}</td><td><span className={styles.rechargeAmount}>+{formatEuro(entry.amount)}</span></td><td>{formatEuro(entry.balanceAfter)}</td><td>
                      {entry.receipt ? <button className={styles.receiptThumb} onClick={() => setReceiptPreview({ url: getRechargeReceiptUrl(detailUser.id, entry.id), name: entry.receipt?.originalFilename || "Receipt" })} type="button"><img alt={entry.receipt.originalFilename} src={getRechargeReceiptUrl(detailUser.id, entry.id)} /><Eye aria-hidden="true" size={14} /></button> : <span className={styles.noReceipt}>No receipt</span>}
                    </td></tr>
                  ))}
                </tbody></table>
              </div>
            ) : <div className={styles.modalEmpty}><WalletCards aria-hidden="true" size={26} /><strong>No recharge records</strong><span>Add the first account recharge for this customer.</span></div>}
          </section>
        </div>
      )}

      {isRechargeOpen && detailUser && (
        <div className={styles.modalBackdropTop} role="presentation">
          <form aria-labelledby="recharge-title" aria-modal="true" className={styles.rechargeModal} onSubmit={handleRecharge} role="dialog">
            <header className={styles.modalHeader}>
              <div><p>Balance adjustment</p><h3 id="recharge-title">Recharge {detailUser.email}</h3></div>
              <button aria-label="Close recharge" className={styles.iconButton} onClick={() => setIsRechargeOpen(false)} type="button"><X aria-hidden="true" size={18} /></button>
            </header>
            <label>Recharge amount (EUR)<input inputMode="decimal" min="0.01" onChange={(event) => setRechargeAmount(event.target.value)} placeholder="0.00" required step="0.01" type="number" value={rechargeAmount} /></label>
            <label className={styles.receiptUpload}><ImageIcon aria-hidden="true" size={22} /><strong>Customer payment receipt</strong><span>Optional · JPG, PNG or WebP · up to 10 MB</span><input accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp" onChange={(event) => setReceiptFile(event.target.files?.[0] ?? null)} type="file" /><small>{receiptFile ? receiptFile.name : "No image selected"}</small></label>
            <footer><button onClick={() => setIsRechargeOpen(false)} type="button">Cancel</button><button disabled={isRecharging} type="submit">{isRecharging ? "Adding recharge..." : "Add recharge"}</button></footer>
          </form>
        </div>
      )}

      {receiptPreview && (
        <div className={styles.imageViewer} onClick={() => setReceiptPreview(null)} role="presentation">
          <section aria-label="Receipt preview" aria-modal="true" onClick={(event) => event.stopPropagation()} role="dialog">
            <header><strong>{receiptPreview.name}</strong><button aria-label="Close receipt preview" onClick={() => setReceiptPreview(null)} type="button"><X aria-hidden="true" size={18} /></button></header>
            <img alt={receiptPreview.name} src={receiptPreview.url} />
          </section>
        </div>
      )}
    </AppShell>
  );
}

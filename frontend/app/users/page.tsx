"use client";
/* eslint-disable @next/next/no-img-element */

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowDownRight,
  ArrowUpLeft,
  FileDown,
  Eye,
  ImageIcon,
  Plus,
  ReceiptText,
  WalletCards,
  X
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { InvoicePanel } from "@/components/InvoicePanel";
import { AppMessage } from "@/components/InfoCenter";
import {
  cancelDeduction,
  cancelRecharge,
  createUser,
  deleteUser,
  exportBillingAccount,
  getCurrentUser,
  getRechargeReceiptUrl,
  getUserBillingAccount,
  isUnauthorizedError,
  listUsers,
  logout,
  rechargeUser,
  resetUserPassword,
  updateUserPayer,
  updateUserStatus
} from "@/lib/api";
import type { AppUser, BillingAccountResponse, BillingEntryItem } from "@/lib/types";
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
  const [billingTab, setBillingTab] = useState<"deductions" | "recharges" | "invoices">("deductions");
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [isRechargeOpen, setIsRechargeOpen] = useState(false);
  const [rechargeAmount, setRechargeAmount] = useState("");
  const [receiptFile, setReceiptFile] = useState<File | null>(null);
  const [isRecharging, setIsRecharging] = useState(false);
  const [cancellingDeductionId, setCancellingDeductionId] = useState<string | null>(null);
  const [cancellingRechargeId, setCancellingRechargeId] = useState<string | null>(null);
  const [isExportingBilling, setIsExportingBilling] = useState(false);
  const [receiptPreview, setReceiptPreview] = useState<{ url: string; name: string } | null>(null);
  const [payerCompany, setPayerCompany] = useState("");
  const [payerAddress, setPayerAddress] = useState("");
  const [isPayerSaving, setIsPayerSaving] = useState(false);

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
      setPayerCompany(account.user.payerCompanyName || "");
      setPayerAddress(account.user.payerAddressInfo || "");
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

  const handleExportBilling = useCallback(async () => {
    if (!detailUser) return;
    setIsExportingBilling(true);
    setDetailError(null);
    try {
      await exportBillingAccount(detailUser.id);
    } catch (error) {
      if (isUnauthorizedError(error)) {
        router.replace("/");
        return;
      }
      setDetailError(
        error instanceof Error ? error.message : "Unable to export billing details"
      );
    } finally {
      setIsExportingBilling(false);
    }
  }, [detailUser, router]);

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

  async function handleSavePayer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detailUser) return;
    setIsPayerSaving(true);
    try {
      const updated = await updateUserPayer(detailUser.id, payerCompany, payerAddress);
      setDetailUser(updated);
      setBilling((current) => current ? { ...current, user: updated } : current);
      await refreshUsers();
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : "Unable to save payer information");
    } finally { setIsPayerSaving(false); }
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

  async function handleCancelDeduction(entry: BillingEntryItem) {
    if (!detailUser || entry.entryType !== "deduction" || entry.reversedByEntryId) {
      return;
    }
    const confirmed = window.confirm(
      `Cancel customs tax for ${entry.waybillNumber || "this waybill"}? ${formatEuro(entry.amount)} will be returned to the customer balance.`
    );
    if (!confirmed) return;

    setCancellingDeductionId(entry.id);
    setDetailError(null);
    try {
      const account = await cancelDeduction(detailUser.id, entry.id);
      setBilling(account);
      setDetailUser(account.user);
      await refreshUsers();
    } catch (error) {
      if (isUnauthorizedError(error)) {
        router.replace("/");
        return;
      }
      setDetailError(
        error instanceof Error ? error.message : "Unable to cancel customs tax"
      );
    } finally {
      setCancellingDeductionId(null);
    }
  }

  async function handleCancelRecharge(entry: BillingEntryItem) {
    if (!detailUser || entry.entryType !== "recharge" || entry.reversedByEntryId) {
      return;
    }
    const confirmed = window.confirm(
      `Cancel this recharge of ${formatEuro(entry.amount)}? The amount will be deducted from the customer balance and the balance may become negative.`
    );
    if (!confirmed) return;

    setCancellingRechargeId(entry.id);
    setDetailError(null);
    try {
      const account = await cancelRecharge(detailUser.id, entry.id);
      setBilling(account);
      setDetailUser(account.user);
      setBillingTab("recharges");
      await refreshUsers();
    } catch (error) {
      if (isUnauthorizedError(error)) {
        router.replace("/");
        return;
      }
      setDetailError(
        error instanceof Error ? error.message : "Unable to cancel recharge"
      );
    } finally {
      setCancellingRechargeId(null);
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

            <form className={styles.resetPanel} onSubmit={handleSavePayer}>
              <strong>Payer information</strong>
              <input aria-label="Payer company name" onChange={(event) => setPayerCompany(event.target.value)} placeholder="Company name" required value={payerCompany} />
              <textarea aria-label="Payer address information" onChange={(event) => setPayerAddress(event.target.value)} placeholder="Address / legal information" required value={payerAddress} />
              <button disabled={isPayerSaving} type="submit">{isPayerSaving ? "Saving..." : "Save payer"}</button>
            </form>

            <div className={styles.billingToolbar}>
              <div className={styles.tabs} role="tablist" aria-label="Customer billing sections">
                <button aria-selected={billingTab === "deductions"} data-active={billingTab === "deductions"} onClick={() => setBillingTab("deductions")} role="tab" type="button">Deduction entries</button>
                <button aria-selected={billingTab === "recharges"} data-active={billingTab === "recharges"} onClick={() => setBillingTab("recharges")} role="tab" type="button">Recharge records</button>
                <button aria-selected={billingTab === "invoices"} data-active={billingTab === "invoices"} onClick={() => setBillingTab("invoices")} role="tab" type="button">Uninvoiced waybills</button>
              </div>
              {billingTab === "recharges" && (
                <button className={styles.rechargeButton} onClick={() => setIsRechargeOpen(true)} type="button"><Plus aria-hidden="true" size={16} />Recharge</button>
              )}
              {billingTab === "deductions" && (
                <button
                  className={styles.exportButton}
                  disabled={isExportingBilling}
                  onClick={() => void handleExportBilling()}
                  type="button"
                >
                  <FileDown aria-hidden="true" size={16} />
                  {isExportingBilling ? "Exporting..." : "Export Excel"}
                </button>
              )}
            </div>

            {detailError && <div className={styles.modalError} role="alert">{detailError}</div>}
            {isDetailLoading ? (
              <div className={styles.modalEmpty}>Loading customer billing...</div>
            ) : billingTab === "invoices" ? (
              <InvoicePanel admin userId={detailUser.id} />
            ) : billingTab === "deductions" ? (
              billing?.deductions.length ? (
                <div className={styles.ledgerTableWrap}>
                  <table><thead><tr><th>Air Waybill Number</th><th>Supplier</th><th>Source</th><th>Calculation</th><th>Recorded At</th><th>Amount</th><th>Balance After</th><th>Action</th></tr></thead><tbody>
                    {billing.deductions.map((entry) => {
                      const isReversal = entry.entryType === "deduction_reversal";
                      return (
                        <tr className={isReversal ? styles.reversalRow : undefined} key={entry.id}>
                          <td>{entry.waybillNumber || "-"}</td>
                          <td>{entry.supplierName ? `${entry.supplierName} v${entry.supplierVersionNumber}` : "-"}</td>
                          <td>{isReversal ? "Tax cancellation" : entry.billingSource === "retroactive" ? "Tax backfill" : "Upload"}</td>
                          <td>{entry.billableUnitCount != null && entry.unitRate ? `${entry.billableUnitCount} × ${formatEuro(entry.unitRate)}` : "-"}</td>
                          <td>{formatDateTime(entry.createdAt)}</td>
                          <td>
                            {isReversal ? (
                              <div className={styles.cancellationAmountWrap}>
                                <span className={styles.cancellationAmount}><ArrowUpLeft aria-hidden="true" size={14} />+{formatEuro(entry.amount)}</span>
                                <span className={styles.cancellationTag}>Tax cancelled</span>
                              </div>
                            ) : (
                              <span className={styles.deductionAmount}><ArrowDownRight aria-hidden="true" size={14} />{formatEuro(entry.amount)}</span>
                            )}
                          </td>
                          <td>{formatEuro(entry.balanceAfter)}</td>
                          <td>
                            {isReversal ? (
                              <span className={styles.ledgerNote}>Refund record</span>
                            ) : entry.reversedByEntryId ? (
                              <span className={styles.cancelledTag}>Cancelled</span>
                            ) : (
                              <button
                                className={styles.cancelTaxButton}
                                disabled={cancellingDeductionId === entry.id}
                                onClick={() => void handleCancelDeduction(entry)}
                                type="button"
                              >
                                {cancellingDeductionId === entry.id ? "Cancelling..." : "Cancel tax"}
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody></table>
                </div>
              ) : <div className={styles.modalEmpty}><ReceiptText aria-hidden="true" size={26} /><strong>No deduction entries</strong><span>Posted waybill tax charges will appear here.</span></div>
            ) : billing?.recharges.length ? (
              <div className={styles.ledgerTableWrap}>
                <table><thead><tr><th>Recharge Time</th><th>Type</th><th>Amount</th><th>Balance After</th><th>Receipt</th><th>Action</th></tr></thead><tbody>
                  {billing.recharges.map((entry) => {
                    const isReversal = entry.entryType === "recharge_reversal";
                    return (
                      <tr className={isReversal ? styles.rechargeReversalRow : undefined} key={entry.id}>
                        <td>{formatDateTime(entry.createdAt)}</td>
                        <td>{isReversal ? <span className={styles.rechargeCancellationTag}>Recharge cancellation</span> : "Recharge"}</td>
                        <td>
                          {isReversal ? (
                            <span className={styles.rechargeReversalAmount}><ArrowDownRight aria-hidden="true" size={14} />-{formatEuro(entry.amount)}</span>
                          ) : (
                            <span className={styles.rechargeAmount}>+{formatEuro(entry.amount)}</span>
                          )}
                        </td>
                        <td>{formatEuro(entry.balanceAfter)}</td>
                        <td>
                          {isReversal ? (
                            <span className={styles.ledgerNote}>Correction record</span>
                          ) : entry.receipt ? (
                            <button className={styles.receiptThumb} onClick={() => setReceiptPreview({ url: getRechargeReceiptUrl(detailUser.id, entry.id), name: entry.receipt?.originalFilename || "Receipt" })} type="button"><img alt={entry.receipt.originalFilename} src={getRechargeReceiptUrl(detailUser.id, entry.id)} /><Eye aria-hidden="true" size={14} /></button>
                          ) : (
                            <span className={styles.noReceipt}>No receipt</span>
                          )}
                        </td>
                        <td>
                          {isReversal ? (
                            <span className={styles.ledgerNote}>Reversal record</span>
                          ) : entry.reversedByEntryId ? (
                            <span className={styles.cancelledTag}>Cancelled</span>
                          ) : (
                            <button
                              className={styles.cancelTaxButton}
                              disabled={cancellingRechargeId === entry.id}
                              onClick={() => void handleCancelRecharge(entry)}
                              type="button"
                            >
                              {cancellingRechargeId === entry.id ? "Cancelling..." : "Cancel recharge"}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
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

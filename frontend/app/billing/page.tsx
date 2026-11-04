"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowDownRight, ArrowUpLeft, FileDown, ReceiptText, RefreshCw, WalletCards } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { InvoicePanel } from "@/components/InvoicePanel";
import {
  exportBillingAccount,
  getMyBillingAccount,
  isUnauthorizedError,
  logout
} from "@/lib/api";
import type { AppUser, BillingEntryItem } from "@/lib/types";
import styles from "./page.module.css";

function formatEuro(value: string) {
  return new Intl.NumberFormat("en-IE", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2
  }).format(Number(value));
}
function money(value: string, currency = "EUR") {
  return new Intl.NumberFormat("en-GB", { style: "currency", currency }).format(Number(value));
}
function feeName(type?: string | null) {
  return ({ customs_tax: "Customs tax", declaration_operation_fee: "申报行操作费", lhr_weight_handling: "LHR 操作费", lhr_clearance: "LHR 清关费" } as Record<string, string>)[type || "customs_tax"] || "Fee";
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

export default function BillingPage() {
  const router = useRouter();
  const [user, setUser] = useState<AppUser | null>(null);
  const [deductions, setDeductions] = useState<BillingEntryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  const loadAccount = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const account = await getMyBillingAccount();
      if (account.user.role === "admin") {
        router.replace("/users");
        return;
      }
      setUser(account.user);
      setDeductions(account.deductions);
    } catch (loadError) {
      if (isUnauthorizedError(loadError)) {
        router.replace("/");
        return;
      }
      setError(
        loadError instanceof Error ? loadError.message : "Unable to load billing account"
      );
    } finally {
      setIsLoading(false);
    }
  }, [router]);

  useEffect(() => {
    void loadAccount();
  }, [loadAccount]);

  const handleExport = useCallback(async () => {
    setIsExporting(true);
    setError(null);
    try {
      await exportBillingAccount();
    } catch (exportError) {
      if (isUnauthorizedError(exportError)) {
        router.replace("/");
        return;
      }
      setError(
        exportError instanceof Error
          ? exportError.message
          : "Unable to export billing details"
      );
    } finally {
      setIsExporting(false);
    }
  }, [router]);

  if (isLoading && !user) {
    return <main className={styles.loadingPage}>Loading billing account...</main>;
  }

  if (!user) {
    return (
      <main className={styles.loadingPage}>
        <p>{error || "Billing account unavailable"}</p>
        <button onClick={() => void loadAccount()} type="button">Try again</button>
      </main>
    );
  }

  return (
    <AppShell
      active="billing"
      isInfoOpen={false}
      messages={[]}
      onInfoClose={() => undefined}
      onInfoOpen={() => undefined}
      onLogout={async () => {
        await logout();
        router.replace("/");
      }}
      unreadCount={0}
      user={user}
    >
      <section className={styles.workspace}>
        <header className={styles.header}>
          <div>
            <p>Account ledger</p>
            <h2>Billing</h2>
          </div>
          <button disabled={isLoading} onClick={() => void loadAccount()} type="button">
            <RefreshCw aria-hidden="true" size={16} />
            Refresh
          </button>
        </header>

        <section className={styles.balanceCard}>
          <div className={styles.balanceIcon}>
            <WalletCards aria-hidden="true" size={26} />
          </div>
          <div>
            <span>Available balance</span>
            <strong>{formatEuro(user.balance)} · {money(user.gbpBalance || "0.00", "GBP")}</strong>
            <small>EUR / GBP accounts · updated from your posted ledger</small>
          </div>
          <div className={styles.balanceMark}>EPIX / EUR + GBP</div>
        </section>

        {error && <div className={styles.errorNotice} role="alert">{error}</div>}

        <section className={styles.ledgerCard}>
          <div className={styles.ledgerHeader}>
            <div>
              <p>Customer billing</p>
              <h3>Deduction entries</h3>
            </div>
            <div className={styles.ledgerActions}>
              <span>{deductions.length} records</span>
              <button
                disabled={isExporting}
                onClick={() => void handleExport()}
                type="button"
              >
                <FileDown aria-hidden="true" size={16} />
                {isExporting ? "Exporting..." : "Export Excel"}
              </button>
            </div>
          </div>

          {deductions.length ? (
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Air Waybill Number</th>
                    <th>Fee type</th><th>Supplier</th>
                    <th>Source</th>
                    <th>Calculation</th>
                    <th>Recorded At</th>
                    <th>Amount</th>
                    <th>Balance After</th>
                  </tr>
                </thead>
                <tbody>
                  {deductions.map((entry) => {
                    const isReversal = entry.entryType === "deduction_reversal";
                    return (
                    <tr className={isReversal ? styles.reversalRow : undefined} key={entry.id}>
                      <td>
                        <span className={styles.waybillCell}>
                          <ReceiptText aria-hidden="true" size={16} />
                          {entry.waybillNumber || "-"}
                        </span>
                      </td>
                      <td>{feeName(entry.feeType)}</td>
                          <td>{entry.supplierName ? `${entry.supplierName} v${entry.supplierVersionNumber}` : "-"}</td>
                      <td>{isReversal ? (!entry.feeType || entry.feeType === "customs_tax" ? "Tax cancellation" : "Fee cancellation") : entry.billingSource === "retroactive" ? (!entry.feeType || entry.feeType === "customs_tax" ? "Tax backfill" : "Fee backfill") : "Upload"}</td>
                      <td>{(entry.quantity ?? entry.billableUnitCount) != null && entry.unitRate ? `${entry.quantity ?? entry.billableUnitCount} × ${money(entry.unitRate, entry.currency)}` : "-"}</td>
                      <td>{formatDateTime(entry.createdAt)}</td>
                      <td>
                        {isReversal ? (
                          <span className={styles.refundAmount}>
                            <ArrowUpLeft aria-hidden="true" size={15} />
                            +{money(entry.amount, entry.currency)}
                            <small>{!entry.feeType || entry.feeType === "customs_tax" ? "Tax cancelled" : "Fee cancelled"}</small>
                          </span>
                        ) : (
                          <span className={styles.chargeAmount}>
                            <ArrowDownRight aria-hidden="true" size={15} />
                            {money(entry.amount, entry.currency)}
                          </span>
                        )}
                      </td>
                      <td>{money(entry.balanceAfter, entry.currency)}</td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className={styles.emptyState}>
              <ReceiptText aria-hidden="true" size={28} />
              <strong>No deduction entries yet</strong>
              <span>Customs tax and declaration operation fees will appear here after they are posted to a waybill.</span>
            </div>
          )}
        </section>
        <InvoicePanel />
      </section>
    </AppShell>
  );
}

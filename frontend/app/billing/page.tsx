"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowDownRight, ReceiptText, RefreshCw, WalletCards } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import {
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
            <strong>{formatEuro(user.balance)}</strong>
            <small>EUR account · updated from your posted ledger</small>
          </div>
          <div className={styles.balanceMark}>EPIX / EUR</div>
        </section>

        {error && <div className={styles.errorNotice} role="alert">{error}</div>}

        <section className={styles.ledgerCard}>
          <div className={styles.ledgerHeader}>
            <div>
              <p>Customer billing</p>
              <h3>Deduction entries</h3>
            </div>
            <span>{deductions.length} records</span>
          </div>

          {deductions.length ? (
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Air Waybill Number</th>
                    <th>Supplier</th>
                    <th>Source</th>
                    <th>Calculation</th>
                    <th>Deducted At</th>
                    <th>Amount</th>
                    <th>Balance After</th>
                  </tr>
                </thead>
                <tbody>
                  {deductions.map((entry) => (
                    <tr key={entry.id}>
                      <td>
                        <span className={styles.waybillCell}>
                          <ReceiptText aria-hidden="true" size={16} />
                          {entry.waybillNumber || "-"}
                        </span>
                      </td>
                      <td>{entry.supplierName ? `${entry.supplierName} v${entry.supplierVersionNumber}` : "-"}</td>
                      <td>{entry.billingSource === "retroactive" ? "Tax backfill" : "Upload"}</td>
                      <td>{entry.billableUnitCount != null && entry.unitRate ? `${entry.billableUnitCount} × ${formatEuro(entry.unitRate)}` : "-"}</td>
                      <td>{formatDateTime(entry.createdAt)}</td>
                      <td>
                        <span className={styles.chargeAmount}>
                          <ArrowDownRight aria-hidden="true" size={15} />
                          {formatEuro(entry.amount)}
                        </span>
                      </td>
                      <td>{formatEuro(entry.balanceAfter)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className={styles.emptyState}>
              <ReceiptText aria-hidden="true" size={28} />
              <strong>No deduction entries yet</strong>
              <span>Tax charges will appear here after they are posted to a waybill.</span>
            </div>
          )}
        </section>
      </section>
    </AppShell>
  );
}

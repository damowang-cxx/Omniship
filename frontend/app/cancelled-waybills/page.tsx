"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArchiveX, CircleDollarSign, RefreshCw, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import type { AppMessage } from "@/components/InfoCenter";
import {
  getCurrentUser,
  isUnauthorizedError,
  listCancelledWaybills,
  logout
} from "@/lib/api";
import type { AppUser, CancelledWaybillItem } from "@/lib/types";
import styles from "./page.module.css";

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

function formatMoney(value: string, currency = "EUR") {
  const number = Number(value);
  if (!Number.isFinite(number)) return `${currency} ${value}`;
  return new Intl.NumberFormat("en-IE", {
    style: "currency",
    currency
  }).format(number);
}

export default function CancelledWaybillsPage() {
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<AppUser | null>(null);
  const [items, setItems] = useState<CancelledWaybillItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<AppMessage[]>([]);
  const [isInfoOpen, setIsInfoOpen] = useState(false);

  const loadRecords = useCallback(async (refresh = false) => {
    if (refresh) setIsRefreshing(true);
    try {
      const response = await listCancelledWaybills();
      setItems(response.items);
      setError(null);
    } catch (loadError) {
      if (isUnauthorizedError(loadError)) {
        router.replace("/");
        return;
      }
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Unable to load cancelled waybills"
      );
    } finally {
      if (refresh) setIsRefreshing(false);
    }
  }, [router]);

  useEffect(() => {
    async function bootstrap() {
      try {
        const response = await getCurrentUser();
        setCurrentUser(response.user);
        if (response.user.role !== "admin") {
          router.replace("/waybills");
          return;
        }
        await loadRecords();
      } catch (bootstrapError) {
        setError(
          bootstrapError instanceof Error
            ? bootstrapError.message
            : "Unable to load account information"
        );
        router.replace("/");
      } finally {
        setIsLoading(false);
      }
    }
    void bootstrap();
  }, [loadRecords, router]);

  const totals = useMemo(
    () =>
      items.reduce(
        (summary, item) => ({
          taxDeleted: summary.taxDeleted + Number(item.taxAmountDeleted || 0),
          refunded: summary.refunded + Number(item.refundedAmount || 0)
        }),
        { taxDeleted: 0, refunded: 0 }
      ),
    [items]
  );

  const handleLogout = useCallback(async () => {
    await logout();
    router.replace("/");
  }, [router]);

  if (isLoading) {
    return (
      <main className={styles.loadingPage}>
        <ArchiveX aria-hidden="true" size={24} />
        Loading cancellation records...
      </main>
    );
  }

  if (!currentUser || currentUser.role !== "admin") {
    return <main className={styles.loadingPage}>Admin permission required.</main>;
  }

  return (
    <AppShell
      active="cancelled-waybills"
      isInfoOpen={isInfoOpen}
      messages={messages}
      onInfoClose={() => setIsInfoOpen(false)}
      onInfoOpen={() => {
        setIsInfoOpen(true);
        setMessages((current) => current.map((message) => ({ ...message, read: true })));
      }}
      onLogout={handleLogout}
      unreadCount={messages.filter((message) => !message.read).length}
      user={currentUser}
    >
      <section className={styles.workspace}>
        <header className={styles.pageHeader}>
          <div>
            <p className={styles.eyebrow}>Administrator audit trail</p>
            <h2>Cancelled Waybills</h2>
            <p>
              Permanent snapshots of removed waybills and their customs refunds.
            </p>
          </div>
          <button
            disabled={isRefreshing}
            onClick={() => void loadRecords(true)}
            type="button"
          >
            <RefreshCw aria-hidden="true" size={16} />
            {isRefreshing ? "Refreshing..." : "Refresh"}
          </button>
        </header>

        <div className={styles.summaryGrid}>
          <article>
            <span className={styles.summaryIcon}>
              <ArchiveX aria-hidden="true" size={19} />
            </span>
            <div>
              <small>Cancelled records</small>
              <strong>{items.length}</strong>
            </div>
          </article>
          <article>
            <span className={styles.summaryIcon}>
              <ShieldCheck aria-hidden="true" size={19} />
            </span>
            <div>
              <small>Tax records removed</small>
              <strong>{formatMoney(totals.taxDeleted.toFixed(2))}</strong>
            </div>
          </article>
          <article>
            <span className={styles.summaryIcon}>
              <CircleDollarSign aria-hidden="true" size={19} />
            </span>
            <div>
              <small>Returned to balances</small>
              <strong>{formatMoney(totals.refunded.toFixed(2))}</strong>
            </div>
          </article>
        </div>

        {error && (
          <div className={styles.errorBanner} role="alert">
            {error}
          </div>
        )}

        <section className={styles.recordCard}>
          <div className={styles.recordHeader}>
            <div>
              <p className={styles.eyebrow}>Cancellation ledger</p>
              <h3>Archived records</h3>
            </div>
            <span>{items.length} total</span>
          </div>

          {items.length ? (
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Waybill</th>
                    <th>Customer</th>
                    <th>Supplier</th>
                    <th>Route</th>
                    <th>Original status</th>
                    <th>Tax removed</th>
                    <th>Refunded</th>
                    <th>Balance after</th>
                    <th>Cancelled by</th>
                    <th>Cancelled at</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>{item.airWaybillNumber}</strong>
                        <small>Uploaded {formatDateTime(item.uploadedAt)}</small>
                      </td>
                      <td>
                        <span>{item.userEmail}</span>
                        <small>{item.username}</small>
                      </td>
                      <td>
                        {item.supplierName
                          ? `${item.supplierName} v${item.supplierVersionNumber ?? "-"}`
                          : "-"}
                      </td>
                      <td>
                        {item.airportOfDeparture || "-"}
                        <span className={styles.routeArrow}>→</span>
                        {item.airportOfArrival || "-"}
                      </td>
                      <td>
                        <span className={styles.statusPill}>
                          {item.originalStatus.replace("_", " ")}
                        </span>
                      </td>
                      <td>{formatMoney(item.taxAmountDeleted, item.currency)}</td>
                      <td>
                        <strong className={styles.refundValue}>
                          +{formatMoney(item.refundedAmount, item.currency)}
                        </strong>
                      </td>
                      <td>
                        {item.balanceAfterRefund == null
                          ? "-"
                          : formatMoney(item.balanceAfterRefund, item.currency)}
                      </td>
                      <td>{item.cancelledByEmail}</td>
                      <td>{formatDateTime(item.cancelledAt)}</td>
                      <td>
                        <span className={styles.reason}>{item.reason}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className={styles.emptyState}>
              <ArchiveX aria-hidden="true" size={28} />
              <strong>No cancelled waybills</strong>
              <span>Cancelled records will remain available here for audit.</span>
            </div>
          )}
        </section>
      </section>
    </AppShell>
  );
}

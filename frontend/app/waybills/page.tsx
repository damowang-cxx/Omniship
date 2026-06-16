"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { X } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { AppMessage } from "@/components/InfoCenter";
import {
  getCurrentUser,
  isUnauthorizedError,
  listUsers,
  listWaybills,
  logout,
  updateWaybill
} from "@/lib/api";
import type {
  AppUser,
  WaybillFycoStatus,
  WaybillFilters,
  WaybillItem,
  WaybillTrackingStatus
} from "@/lib/types";
import styles from "./page.module.css";

const statusOptions: { value: WaybillTrackingStatus; label: string }[] = [
  { value: "created", label: "Created" },
  { value: "noa_received", label: "NOA Received" },
  { value: "received", label: "Received" },
  { value: "ready_to_scan", label: "Ready To Scan" },
  { value: "scanning", label: "Scanning" },
  { value: "pending_clearance", label: "Pending Clearance" },
  { value: "cleared", label: "Cleared" },
  { value: "partial_inbound", label: "Partial Inbound" },
  { value: "inbound", label: "Inbound" },
  { value: "partial_outbound", label: "Partial Outbound" },
  { value: "outbound", label: "Outbound" }
];

const initialFilters: {
  userId: string;
  status: WaybillTrackingStatus | "";
  q: string;
} = {
  userId: "",
  status: "",
  q: ""
};

const fycoOptions: { value: WaybillFycoStatus; label: string }[] = [
  { value: "released", label: "Released" },
  { value: "fyco", label: "Fyco" }
];

type EditForm = {
  status: WaybillTrackingStatus;
  receivedCount: string;
  receivedTotal: string;
  inWarehouseCount: string;
  palletCount: string;
  fycoStatus: WaybillFycoStatus;
  releasedCount: string;
  outboundCount: string;
};

function statusLabel(status: WaybillTrackingStatus) {
  return statusOptions.find((option) => option.value === status)?.label ?? status;
}

function fycoLabel(status: WaybillFycoStatus) {
  return fycoOptions.find((option) => option.value === status)?.label ?? status;
}

function formatStatusAge(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  const diffMs = Date.now() - date.getTime();
  const hours = Math.floor(diffMs / (1000 * 60 * 60));
  if (hours < 1) {
    return "less than an hour ago";
  }
  if (hours < 24) {
    return `${hours} hours ago`;
  }
  return `${Math.max(1, Math.floor(hours / 24))} days ago`;
}

function formatProgress(count: number, pieces: number) {
  const percent = pieces > 0 ? (count / pieces) * 100 : 0;
  return `${percent.toFixed(2)}% (${count})`;
}

function progressTone(count: number, pieces: number) {
  if (count <= 0) {
    return "muted";
  }
  if (pieces > 0 && count >= pieces) {
    return "good";
  }
  return "warn";
}

function parseNonNegativeInteger(value: string, label: string) {
  if (!/^\d+$/.test(value.trim())) {
    throw new Error(`${label} must be a non-negative integer`);
  }
  return Number(value.trim());
}

export default function WaybillsPage() {
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<AppUser | null>(null);
  const [users, setUsers] = useState<AppUser[]>([]);
  const [waybills, setWaybills] = useState<WaybillItem[]>([]);
  const [authError, setAuthError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingWaybills, setIsLoadingWaybills] = useState(false);
  const [filters, setFilters] = useState(initialFilters);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [messages, setMessages] = useState<AppMessage[]>([]);
  const [isInfoOpen, setIsInfoOpen] = useState(false);
  const [editingWaybill, setEditingWaybill] = useState<WaybillItem | null>(null);
  const [editForm, setEditForm] = useState<EditForm | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const isAdmin = currentUser?.role === "admin";

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

  const buildFilters = useCallback(
    (filterValues: typeof initialFilters = filters): WaybillFilters => {
      const requestFilters: WaybillFilters = {};
      if (filterValues.userId && isAdmin) {
        requestFilters.userId = filterValues.userId;
      }
      if (filterValues.status) {
        requestFilters.status = filterValues.status;
      }
      if (filterValues.q.trim()) {
        requestFilters.q = filterValues.q.trim();
      }
      return requestFilters;
    },
    [filters, isAdmin]
  );

  const refreshWaybills = useCallback(
    async (filterOverride?: typeof initialFilters) => {
      setIsLoadingWaybills(true);
      try {
        const response = await listWaybills(buildFilters(filterOverride));
        setWaybills(response.items);
      } catch (error) {
        if (isUnauthorizedError(error)) {
          router.replace("/");
          return;
        }
        const message = error instanceof Error ? error.message : "Unable to load waybills";
        setNotice({ tone: "error", text: message });
        addMessage("Waybills failed", message);
      } finally {
        setIsLoadingWaybills(false);
      }
    },
    [addMessage, buildFilters, router]
  );

  useEffect(() => {
    async function bootstrap() {
      try {
        const response = await getCurrentUser();
        setCurrentUser(response.user);
        const requests: [Promise<{ items: WaybillItem[] }>, Promise<{ items: AppUser[] }> | null] = [
          listWaybills({}),
          response.user.role === "admin" ? listUsers() : null
        ];
        const [waybillsResponse, usersResponse] = await Promise.all(requests);
        setWaybills(waybillsResponse.items);
        if (usersResponse) {
          setUsers(usersResponse.items);
        }
      } catch (error) {
        setAuthError(
          error instanceof Error ? error.message : "Unable to load account information"
        );
        router.replace("/");
      } finally {
        setIsLoading(false);
      }
    }

    void bootstrap();
  }, [router]);

  const handleApplyFilters = useCallback(async () => {
    await refreshWaybills();
  }, [refreshWaybills]);

  const handleResetFilters = useCallback(async () => {
    setFilters(initialFilters);
    await refreshWaybills(initialFilters);
  }, [refreshWaybills]);

  const openEditDialog = useCallback((waybill: WaybillItem) => {
    setEditingWaybill(waybill);
    setEditForm({
      status: waybill.status,
      receivedCount: String(waybill.receivedCount),
      receivedTotal: String(waybill.receivedTotal),
      inWarehouseCount: String(waybill.inWarehouseCount),
      palletCount: String(waybill.palletCount),
      fycoStatus: waybill.fycoStatus,
      releasedCount: String(waybill.releasedCount),
      outboundCount: String(waybill.outboundCount)
    });
  }, []);

  const closeEditDialog = useCallback(() => {
    if (!isSaving) {
      setEditingWaybill(null);
      setEditForm(null);
    }
  }, [isSaving]);

  const handleSaveEdit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!editingWaybill || !editForm) {
        return;
      }

      setIsSaving(true);
      setNotice(null);
      try {
        const updated = await updateWaybill(editingWaybill.publicCode, {
          status: editForm.status,
          receivedCount: parseNonNegativeInteger(
            editForm.receivedCount,
            "Received count"
          ),
          receivedTotal: parseNonNegativeInteger(
            editForm.receivedTotal,
            "Received total"
          ),
          inWarehouseCount: parseNonNegativeInteger(
            editForm.inWarehouseCount,
            "In Warehouse count"
          ),
          palletCount: parseNonNegativeInteger(
            editForm.palletCount,
            "Pallet Count"
          ),
          fycoStatus: editForm.fycoStatus,
          releasedCount: parseNonNegativeInteger(
            editForm.releasedCount,
            "Released count"
          ),
          outboundCount: parseNonNegativeInteger(
            editForm.outboundCount,
            "Outbound count"
          )
        });
        setWaybills((current) =>
          current.map((item) => (item.id === updated.id ? updated : item))
        );
        setNotice({
          tone: "success",
          text: `Waybill ${updated.number} updated`
        });
        setEditingWaybill(null);
        setEditForm(null);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to update waybill";
        setNotice({ tone: "error", text: message });
        addMessage("Waybill update failed", message);
      } finally {
        setIsSaving(false);
      }
    },
    [addMessage, editForm, editingWaybill]
  );

  const handleLogout = useCallback(async () => {
    await logout();
    router.replace("/");
  }, [router]);

  const unreadCount = useMemo(
    () => messages.filter((message) => !message.read).length,
    [messages]
  );

  if (isLoading) {
    return <main className={styles.loadingPage}>Loading account information...</main>;
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
      active="waybills"
      isInfoOpen={isInfoOpen}
      messages={messages}
      onInfoClose={() => setIsInfoOpen(false)}
      onInfoOpen={() => {
        setIsInfoOpen(true);
        setMessages((current) => current.map((message) => ({ ...message, read: true })));
      }}
      onLogout={handleLogout}
      unreadCount={unreadCount}
      user={currentUser}
    >
      <section className={styles.workspace}>
        <div className={styles.workspaceHeader}>
          <div>
            <p className={styles.eyebrow}>Tracking</p>
            <h2>Waybills</h2>
          </div>
          <span className={styles.accountTag}>
            {isAdmin ? "All approved waybills" : currentUser.email}
          </span>
        </div>

        <section className={styles.waybillPanel}>
          <div className={styles.listHeader}>
            <div>
              <p className={styles.eyebrow}>Operational status</p>
              <h3>Approved waybills</h3>
            </div>
            <button disabled={isLoadingWaybills} onClick={() => void refreshWaybills()} type="button">
              Refresh
            </button>
          </div>

          {notice && (
            <div
              className={styles.notice}
              data-tone={notice.tone}
              role={notice.tone === "error" ? "alert" : "status"}
            >
              {notice.text}
            </div>
          )}

          <div className={`${styles.filterBar} ${isAdmin ? "" : styles.filterBarUser}`}>
            {isAdmin && (
              <label className={styles.filterField}>
                User
                <select
                  aria-label="Filter User"
                  onChange={(event) =>
                    setFilters((current) => ({ ...current, userId: event.target.value }))
                  }
                  value={filters.userId}
                >
                  <option value="">All users</option>
                  {users.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.email}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label className={styles.filterField}>
              Status
              <select
                aria-label="Filter Status"
                onChange={(event) =>
                  setFilters((current) => ({
                    ...current,
                    status: event.target.value as WaybillTrackingStatus | ""
                  }))
                }
                value={filters.status}
              >
                <option value="">All statuses</option>
                {statusOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.filterField}>
              Number
              <input
                aria-label="Filter Number"
                onChange={(event) =>
                  setFilters((current) => ({ ...current, q: event.target.value }))
                }
                placeholder="784-84063276"
                value={filters.q}
              />
            </label>
            <div className={styles.filterActions}>
              <button disabled={isLoadingWaybills} onClick={handleApplyFilters} type="button">
                Apply
              </button>
              <button disabled={isLoadingWaybills} onClick={handleResetFilters} type="button">
                Reset
              </button>
            </div>
          </div>

          {waybills.length ? (
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Number</th>
                    <th>Status</th>
                    <th>Airport of Departure</th>
                    <th>Airport of Arrival</th>
                    <th>Status Changed</th>
                    <th>Weight(kg)</th>
                    <th>Received</th>
                    <th>Parcels</th>
                    <th>Pallet Count</th>
                    <th>In Warehouse</th>
                    <th>Fyco</th>
                    <th>Released</th>
                    <th>Outbound</th>
                  </tr>
                </thead>
                <tbody>
                  {waybills.map((waybill) => {
                    const inWarehouseTone = progressTone(
                      waybill.inWarehouseCount,
                      waybill.pieces
                    );
                    const releasedTone = progressTone(waybill.releasedCount, waybill.pieces);
                    const outboundTone = progressTone(waybill.outboundCount, waybill.pieces);

                    return (
                      <tr key={waybill.id}>
                        <td>
                          <Link
                            className={styles.numberLink}
                            href={`/waybills/${waybill.publicCode}`}
                          >
                            {waybill.number}
                          </Link>
                        </td>
                        <td>
                          {isAdmin ? (
                            <button
                              aria-label={`Edit status ${waybill.number}`}
                              className={styles.statusButton}
                              data-status={waybill.status}
                              onClick={() => openEditDialog(waybill)}
                              type="button"
                            >
                              {statusLabel(waybill.status)}
                            </button>
                          ) : (
                            <span
                              className={styles.statusPill}
                              data-status={waybill.status}
                            >
                              {statusLabel(waybill.status)}
                            </span>
                          )}
                        </td>
                        <td>{waybill.airportOfDeparture || "-"}</td>
                        <td>{waybill.airportOfArrival || "-"}</td>
                        <td>{formatStatusAge(waybill.statusChangedAt)}</td>
                        <td>{waybill.weightKg}</td>
                        <td>
                          {waybill.receivedCount} / {waybill.receivedTotal}
                        </td>
                        <td>
                          <span className={styles.metricLink}>{waybill.pieces}</span>
                        </td>
                        <td>{waybill.palletCount}</td>
                        <td>
                          <span className={styles[`metric${inWarehouseTone === "good" ? "Good" : inWarehouseTone === "warn" ? "Warn" : "Muted"}`]}>
                            {formatProgress(waybill.inWarehouseCount, waybill.pieces)}
                          </span>
                        </td>
                        <td>
                          <span className={styles.fycoPill} data-value={waybill.fycoStatus}>
                            {fycoLabel(waybill.fycoStatus)}
                          </span>
                        </td>
                        <td>
                          <span className={styles[`metric${releasedTone === "good" ? "Good" : releasedTone === "warn" ? "Warn" : "Muted"}`]}>
                            {formatProgress(waybill.releasedCount, waybill.pieces)}
                          </span>
                        </td>
                        <td>
                          <span className={styles[`metric${outboundTone === "good" ? "Good" : outboundTone === "warn" ? "Warn" : "Muted"}`]}>
                            {formatProgress(waybill.outboundCount, waybill.pieces)}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className={styles.emptyState}>
              {isLoadingWaybills ? "Loading waybills..." : "No approved waybills yet"}
            </div>
          )}
        </section>
      </section>

      {editingWaybill && editForm && (
        <div className={styles.dialogBackdrop} role="presentation">
          <form className={styles.editDialog} onSubmit={handleSaveEdit}>
            <div className={styles.dialogHeader}>
              <div>
                <h3>Edit waybill status</h3>
                <p>{editingWaybill.number}</p>
              </div>
              <button
                aria-label="Close edit dialog"
                className={styles.dialogClose}
                onClick={closeEditDialog}
                type="button"
              >
                <X aria-hidden="true" size={18} />
              </button>
            </div>

            <div className={styles.dialogGrid}>
              <label className={styles.dialogField}>
                Status
                <select
                  aria-label="Waybill Status"
                  onChange={(event) =>
                    setEditForm((current) =>
                      current
                        ? {
                            ...current,
                            status: event.target.value as WaybillTrackingStatus
                          }
                        : current
                    )
                  }
                  value={editForm.status}
                >
                  {statusOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className={styles.dialogField}>
                Received Count
                <input
                  min="0"
                  onChange={(event) =>
                    setEditForm((current) =>
                      current ? { ...current, receivedCount: event.target.value } : current
                    )
                  }
                  required
                  type="number"
                  value={editForm.receivedCount}
                />
              </label>
              <label className={styles.dialogField}>
                Received Total
                <input
                  min="0"
                  onChange={(event) =>
                    setEditForm((current) =>
                      current ? { ...current, receivedTotal: event.target.value } : current
                    )
                  }
                  required
                  type="number"
                  value={editForm.receivedTotal}
                />
              </label>
              <label className={styles.dialogField}>
                In Warehouse Count
                <input
                  min="0"
                  onChange={(event) =>
                    setEditForm((current) =>
                      current
                        ? { ...current, inWarehouseCount: event.target.value }
                        : current
                    )
                  }
                  required
                  type="number"
                  value={editForm.inWarehouseCount}
                />
              </label>
              <label className={styles.dialogField}>
                Pallet Count
                <input
                  min="0"
                  onChange={(event) =>
                    setEditForm((current) =>
                      current ? { ...current, palletCount: event.target.value } : current
                    )
                  }
                  required
                  type="number"
                  value={editForm.palletCount}
                />
              </label>
              <label className={styles.dialogField}>
                Fyco
                <select
                  aria-label="Fyco"
                  onChange={(event) =>
                    setEditForm((current) =>
                      current
                        ? {
                            ...current,
                            fycoStatus: event.target.value as WaybillFycoStatus
                          }
                        : current
                    )
                  }
                  value={editForm.fycoStatus}
                >
                  {fycoOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className={styles.dialogField}>
                Released Count
                <input
                  min="0"
                  onChange={(event) =>
                    setEditForm((current) =>
                      current ? { ...current, releasedCount: event.target.value } : current
                    )
                  }
                  required
                  type="number"
                  value={editForm.releasedCount}
                />
              </label>
              <label className={styles.dialogField}>
                Outbound Count
                <input
                  min="0"
                  onChange={(event) =>
                    setEditForm((current) =>
                      current ? { ...current, outboundCount: event.target.value } : current
                    )
                  }
                  required
                  type="number"
                  value={editForm.outboundCount}
                />
              </label>
            </div>

            <div className={styles.dialogFooter}>
              <button disabled={isSaving} onClick={closeEditDialog} type="button">
                Cancel
              </button>
              <button disabled={isSaving} type="submit">
                {isSaving ? "Saving..." : "Save"}
              </button>
            </div>
          </form>
        </div>
      )}
    </AppShell>
  );
}

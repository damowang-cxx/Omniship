"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Check, Download, Eye, Trash2, X } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { AppMessage } from "@/components/InfoCenter";
import {
  deleteWaybillUpload,
  getCurrentUser,
  getWaybillUploadFileDownloadUrl,
  isUnauthorizedError,
  listUsers,
  listWaybillUploads,
  logout,
  updateWaybillUploadStatus
} from "@/lib/api";
import type {
  AppUser,
  WaybillUploadFilters,
  WaybillUploadItem,
  WaybillUploadStatus
} from "@/lib/types";
import styles from "../waybill-uploads/page.module.css";

const initialFilters: {
  userId: string;
  status: WaybillUploadStatus | "";
  q: string;
} = {
  userId: "",
  status: "",
  q: ""
};

function formatDateTime(value?: string | null) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

function statusLabel(status: WaybillUploadStatus) {
  const labels: Record<WaybillUploadStatus, string> = {
    pending_review: "Pending review",
    approved: "Approved",
    rejected: "Rejected"
  };
  return labels[status] ?? status;
}

function fileKindLabel(kind: string) {
  if (kind === "air_waybill_document") {
    return "Air Waybill Document";
  }
  if (kind === "customer_pre_alert") {
    return "Customer Pre Alert";
  }
  return kind;
}

export default function WaybillUploadManagementPage() {
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<AppUser | null>(null);
  const [users, setUsers] = useState<AppUser[]>([]);
  const [uploads, setUploads] = useState<WaybillUploadItem[]>([]);
  const [authError, setAuthError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingUploads, setIsLoadingUploads] = useState(false);
  const [deletingUploadId, setDeletingUploadId] = useState<string | null>(null);
  const [expandedUploadId, setExpandedUploadId] = useState<string | null>(null);
  const [filters, setFilters] = useState(initialFilters);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [messages, setMessages] = useState<AppMessage[]>([]);
  const [isInfoOpen, setIsInfoOpen] = useState(false);

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

  const buildUploadFilters = useCallback(
    (filterValues: typeof initialFilters = filters): WaybillUploadFilters => {
      const requestFilters: WaybillUploadFilters = {};
      if (filterValues.userId) {
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
    [filters]
  );

  const refreshUploads = useCallback(async (
    filterOverride?: typeof initialFilters
  ) => {
    setIsLoadingUploads(true);
    try {
      const response = await listWaybillUploads(buildUploadFilters(filterOverride));
      setUploads(response.items);
    } catch (error) {
      if (isUnauthorizedError(error)) {
        router.replace("/");
        return;
      }
      const message = error instanceof Error ? error.message : "Unable to load uploads";
      setNotice({ tone: "error", text: message });
      addMessage("Upload list failed", message);
    } finally {
      setIsLoadingUploads(false);
    }
  }, [addMessage, buildUploadFilters, router]);

  useEffect(() => {
    async function bootstrap() {
      try {
        const response = await getCurrentUser();
        setCurrentUser(response.user);
        if (response.user.role !== "admin") {
          router.replace("/waybill-uploads");
          return;
        }
        const [usersResponse, uploadsResponse] = await Promise.all([
          listUsers(),
          listWaybillUploads({})
        ]);
        setUsers(usersResponse.items);
        setUploads(uploadsResponse.items);
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
    await refreshUploads();
  }, [refreshUploads]);

  const handleResetFilters = useCallback(async () => {
    setFilters(initialFilters);
    await refreshUploads(initialFilters);
  }, [refreshUploads]);

  const handleReview = useCallback(
    async (uploadId: string, status: WaybillUploadStatus) => {
      try {
        await updateWaybillUploadStatus(uploadId, status);
        setNotice({ tone: "success", text: `Upload marked as ${statusLabel(status)}` });
        await refreshUploads();
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to update upload";
        setNotice({ tone: "error", text: message });
        addMessage("Review failed", message);
      }
    },
    [addMessage, refreshUploads]
  );

  const handleDelete = useCallback(
    async (upload: WaybillUploadItem) => {
      const confirmed = window.confirm(
        `Delete upload record for ${upload.airWaybillNumber}?`
      );
      if (!confirmed) {
        return;
      }

      setDeletingUploadId(upload.id);
      try {
        await deleteWaybillUpload(upload.id);
        setNotice({
          tone: "success",
          text: `Upload deleted for ${upload.airWaybillNumber}`
        });
        await refreshUploads();
      } catch (error) {
        if (isUnauthorizedError(error)) {
          router.replace("/");
          return;
        }
        const message = error instanceof Error ? error.message : "Unable to delete upload";
        setNotice({ tone: "error", text: message });
        addMessage("Delete failed", message);
      } finally {
        setDeletingUploadId(null);
      }
    },
    [addMessage, refreshUploads, router]
  );

  const handleLogout = useCallback(async () => {
    await logout();
    router.replace("/");
  }, [router]);

  const unreadCount = messages.filter((message) => !message.read).length;

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

  if (currentUser.role !== "admin") {
    return (
      <main className={styles.loadingPage}>
        <p>Admin permission required. Redirecting to uploads...</p>
      </main>
    );
  }

  return (
    <AppShell
      active="upload-management"
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
            <p className={styles.eyebrow}>Admin review</p>
            <h2>Waybill Management</h2>
          </div>
          <span className={styles.accountTag}>All submitted waybills</span>
        </div>

        <section className={styles.uploadList}>
          <div className={styles.listHeader}>
            <div>
              <p className={styles.eyebrow}>Submitted waybills</p>
              <h3>Review queue</h3>
            </div>
            <button disabled={isLoadingUploads} onClick={() => void refreshUploads()} type="button">
              Refresh
            </button>
          </div>

          {notice && (
            <div className={styles.notice} data-tone={notice.tone} role={notice.tone === "error" ? "alert" : "status"}>
              {notice.text}
            </div>
          )}

          <div className={styles.filterBar}>
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
            <label className={styles.filterField}>
              Review Status
              <select
                aria-label="Filter Review Status"
                onChange={(event) =>
                  setFilters((current) => ({
                    ...current,
                    status: event.target.value as WaybillUploadStatus | ""
                  }))
                }
                value={filters.status}
              >
                <option value="">All</option>
                <option value="pending_review">Pending review</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
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
              <button disabled={isLoadingUploads} onClick={handleApplyFilters} type="button">
                Apply
              </button>
              <button disabled={isLoadingUploads} onClick={handleResetFilters} type="button">
                Reset
              </button>
            </div>
          </div>

          {uploads.length ? (
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Number</th>
                    <th>Type</th>
                    <th>Supplier</th>
                    <th>Owner</th>
                    <th>Uploaded By</th>
                    <th>Weight</th>
                    <th>Pieces</th>
                    <th>Flight</th>
                    <th>Status</th>
                    <th>Airport of Departure</th>
                    <th>Airport of Arrival</th>
                    <th>Files</th>
                    <th>Uploaded</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {uploads.map((upload) => (
                    <Fragment key={upload.id}>
                      <tr>
                        <td>{upload.airWaybillNumber}</td>
                        <td>{upload.shipmentType}</td>
                        <td>{upload.supplierName ? `${upload.supplierName} v${upload.supplierVersionNumber}` : "-"}</td>
                        <td>{upload.user?.email ?? upload.userId}</td>
                        <td>{upload.uploadedBy?.email ?? upload.uploadedByUserId ?? "-"}</td>
                        <td>{upload.grossWeightKg}</td>
                        <td>{upload.pieces}</td>
                        <td>{upload.arrivalFlightNumber || "-"}</td>
                        <td>
                          <span className={styles.statusPill} data-status={upload.status}>
                            {statusLabel(upload.status)}
                          </span>
                        </td>
                        <td>{upload.airportOfDeparture || "-"}</td>
                        <td>{upload.airportOfArrival || "-"}</td>
                        <td>{upload.files.length}</td>
                        <td>{formatDateTime(upload.createdAt)}</td>
                        <td>
                          <div className={styles.reviewActions}>
                            <button
                              aria-label={`Details ${upload.airWaybillNumber}`}
                              onClick={() =>
                                setExpandedUploadId((current) =>
                                  current === upload.id ? null : upload.id
                                )
                              }
                              type="button"
                            >
                              <Eye aria-hidden="true" size={15} />
                              {upload.validationIssueCount > 0 && (
                                <span className={styles.warningBadge} title={`${upload.validationIssueCount} supplier warnings`}>
                                  !
                                </span>
                              )}
                            </button>
                            <button
                              aria-label={`Approve ${upload.airWaybillNumber}`}
                              disabled={upload.status === "approved"}
                              onClick={() => handleReview(upload.id, "approved")}
                              type="button"
                            >
                              <Check aria-hidden="true" size={15} />
                            </button>
                            <button
                              aria-label={`Reject ${upload.airWaybillNumber}`}
                              disabled={upload.status === "rejected"}
                              onClick={() => handleReview(upload.id, "rejected")}
                              type="button"
                            >
                              <X aria-hidden="true" size={15} />
                            </button>
                            <button
                              aria-label={`Delete local upload ${upload.airWaybillNumber}`}
                              className={styles.dangerButton}
                              disabled={deletingUploadId === upload.id}
                              onClick={() => handleDelete(upload)}
                              type="button"
                            >
                              <Trash2 aria-hidden="true" size={15} />
                            </button>
                          </div>
                        </td>
                      </tr>
                      {expandedUploadId === upload.id && (
                        <tr className={styles.detailRow}>
                          <td colSpan={14}>
                            <div className={styles.detailPanel}>
                              <div className={styles.detailGrid}>
                                <div>
                                  <span>Owner</span>
                                  <strong>{upload.user?.email ?? upload.userId}</strong>
                                </div>
                                <div>
                                  <span>Uploaded By</span>
                                  <strong>{upload.uploadedBy?.email ?? upload.uploadedByUserId ?? "-"}</strong>
                                </div>
                                <div>
                                  <span>Uploaded At</span>
                                  <strong>{formatDateTime(upload.createdAt)}</strong>
                                </div>
                                <div>
                                  <span>Review Status</span>
                                  <strong>{statusLabel(upload.status)}</strong>
                                </div>
                                <div>
                                  <span>Departure</span>
                                  <strong>{upload.airportOfDeparture || "-"}</strong>
                                </div>
                                <div>
                                  <span>Arrival</span>
                                  <strong>{upload.airportOfArrival || "-"}</strong>
                                </div>
                              </div>

                              {upload.validationIssueCount > 0 && (
                                <div className={styles.validationIssuePanel}>
                                  <div className={styles.validationIssueHeader}>
                                    <AlertTriangle aria-hidden="true" size={18} />
                                    <div>
                                      <strong>{upload.validationIssueCount} supplier rule warnings</strong>
                                      <span>Review these issues before approving the waybill.</span>
                                    </div>
                                  </div>
                                  <div className={styles.validationIssueList}>
                                    {upload.validationIssues.map((issue, index) => (
                                      <div key={`${issue.ruleKey}-${issue.rowNumber}-${index}`}>
                                        <strong>Row {issue.rowNumber} · {issue.ruleName} ({issue.column})</strong>
                                        <span>{issue.message}{issue.rawValue ? ` · Value: ${issue.rawValue}` : ""}</span>
                                      </div>
                                    ))}
                                  </div>
                                  {upload.validationIssueCount > upload.validationIssues.length && (
                                    <small>{upload.validationIssueCount - upload.validationIssues.length} additional warnings are not displayed.</small>
                                  )}
                                </div>
                              )}

                              <div className={styles.fileLinks}>
                                <span>Attachments</span>
                                {upload.files.length ? (
                                  upload.files.map((file) => (
                                    <a
                                      href={getWaybillUploadFileDownloadUrl(upload.id, file.id)}
                                      key={file.id}
                                      rel="noreferrer"
                                      target="_blank"
                                    >
                                      <Download aria-hidden="true" size={14} />
                                      {fileKindLabel(file.fileKind)}: {file.originalFilename}
                                    </a>
                                  ))
                                ) : (
                                  <p>No attachments</p>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className={styles.emptyState}>
              {isLoadingUploads ? "Loading uploads..." : "No submitted waybills yet"}
            </div>
          )}
        </section>
      </section>
    </AppShell>
  );
}

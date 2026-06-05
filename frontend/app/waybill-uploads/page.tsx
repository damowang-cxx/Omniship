"use client";

import { Fragment, FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Check,
  Download,
  Eye,
  FileSpreadsheet,
  FileText,
  Trash2,
  UploadCloud,
  X
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import {
  getWaybillUploadFileDownloadUrl,
  getCurrentUser,
  isUnauthorizedError,
  deleteWaybillUpload,
  listUsers,
  listWaybillUploads,
  logout,
  updateWaybillUploadStatus,
  uploadPreAlertFile
} from "@/lib/api";
import type {
  AppUser,
  ShipmentType,
  WaybillUploadFilters,
  WaybillUploadItem,
  WaybillUploadStatus
} from "@/lib/types";
import styles from "./page.module.css";

const PDF_MAX_BYTES = 10 * 1024 * 1024;
const EXCEL_MAX_BYTES = 20 * 1024 * 1024;
const EXCEL_EXTENSIONS = [".xls", ".xlsx"];

const initialForm = {
  shipmentType: "Air" as ShipmentType,
  airWaybillNumber: "",
  grossWeightKg: "",
  pieces: "",
  arrivalFlightNumber: "",
  targetUserId: ""
};

const initialFilters: {
  userId: string;
  status: WaybillUploadStatus | "";
  q: string;
} = {
  userId: "",
  status: "",
  q: ""
};

function hasExtension(file: File, extensions: string[]) {
  const name = file.name.toLowerCase();
  return extensions.some((extension) => name.endsWith(extension));
}

function formatBytes(value: number) {
  if (value < 1024 * 1024) {
    return `${Math.round(value / 1024)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

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

function cleanUploadErrorMessage(error: unknown) {
  const fallback = "Upload failed";
  const rawMessage = error instanceof Error ? error.message : fallback;
  const requestMatch = rawMessage.match(/^Request failed with \d+:\s*([\s\S]*)$/);
  const message = requestMatch?.[1] || rawMessage || fallback;
  return message.replace(/;\s+/g, "\n");
}

function uploadErrorTitle(message: string) {
  return message.includes("Pre Alert validation failed")
    ? "Excel 校验未通过"
    : "上传失败";
}

export default function WaybillUploadsPage() {
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<AppUser | null>(null);
  const [authState, setAuthState] = useState<"loading" | "ready">("loading");
  const [authError, setAuthError] = useState<string | null>(null);
  const [users, setUsers] = useState<AppUser[]>([]);
  const [uploads, setUploads] = useState<WaybillUploadItem[]>([]);
  const [form, setForm] = useState(initialForm);
  const [airWaybillDocuments, setAirWaybillDocuments] = useState<File[]>([]);
  const [preAlertFile, setPreAlertFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingUploads, setIsLoadingUploads] = useState(false);
  const [deletingUploadId, setDeletingUploadId] = useState<string | null>(null);
  const [expandedUploadId, setExpandedUploadId] = useState<string | null>(null);
  const [filters, setFilters] = useState(initialFilters);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [uploadErrorDialog, setUploadErrorDialog] = useState<{
    title: string;
    message: string;
  } | null>(null);

  const isAdmin = currentUser?.role === "admin";

  const buildUploadFilters = useCallback(
    (
      actor: AppUser,
      filterValues: typeof initialFilters = filters
    ): WaybillUploadFilters => {
      const requestFilters: WaybillUploadFilters = {};
      if (filterValues.status) {
        requestFilters.status = filterValues.status;
      }
      if (filterValues.q.trim()) {
        requestFilters.q = filterValues.q.trim();
      }
      if (actor.role === "admin" && filterValues.userId) {
        requestFilters.userId = filterValues.userId;
      }
      return requestFilters;
    },
    [filters]
  );

  const refreshUploads = useCallback(async (
    actorOverride?: AppUser | null,
    filterOverride?: typeof initialFilters
  ) => {
    const actor = actorOverride ?? currentUser;
    if (!actor) {
      return;
    }
    setIsLoadingUploads(true);
    try {
      const response = await listWaybillUploads(buildUploadFilters(actor, filterOverride));
      setUploads(response.items);
    } catch (error) {
      if (isUnauthorizedError(error)) {
        router.replace("/");
        return;
      }
      setNotice({
        tone: "error",
        text: error instanceof Error ? error.message : "Unable to load uploads"
      });
    } finally {
      setIsLoadingUploads(false);
    }
  }, [buildUploadFilters, currentUser, router]);

  useEffect(() => {
    async function loadCurrentUser() {
      try {
        const response = await getCurrentUser();
        setCurrentUser(response.user);
        setForm((current) => ({ ...current, targetUserId: response.user.id }));
        setAuthState("ready");
        const uploadsResponse = await listWaybillUploads({});
        setUploads(uploadsResponse.items);
        if (response.user.role === "admin") {
          const usersResponse = await listUsers();
          setUsers(usersResponse.items.filter((user) => user.status === "active"));
        }
      } catch (error) {
        setAuthError(
          error instanceof Error ? error.message : "无法加载账号信息"
        );
        setAuthState("ready");
        router.replace("/");
      }
    }

    void loadCurrentUser();
  }, [router]);

  const selectedOwner = useMemo(() => {
    if (!currentUser) {
      return null;
    }
    return users.find((user) => user.id === form.targetUserId) ?? currentUser;
  }, [currentUser, form.targetUserId, users]);

  const validateForm = useCallback(() => {
    if (!form.airWaybillNumber.trim()) {
      return "Air Waybill Number is required";
    }
    if (!form.grossWeightKg.trim() || !Number.isFinite(Number(form.grossWeightKg))) {
      return "Air Waybill Gross Weight (KG) must be a number";
    }
    if (!form.pieces.trim() || !/^\d+$/.test(form.pieces.trim())) {
      return "Air Waybill Pieces must be a number";
    }
    if (!airWaybillDocuments.length) {
      return "Air Waybill Document(s) is required";
    }
    for (const file of airWaybillDocuments) {
      if (!hasExtension(file, [".pdf"]) || (file.type && file.type !== "application/pdf")) {
        return "Air Waybill Document(s) must be PDF files";
      }
      if (file.size > PDF_MAX_BYTES) {
        return "Each Air Waybill Document must be smaller than 10 MB";
      }
    }
    if (!preAlertFile) {
      return "Upload Pre Alert File is required";
    }
    if (!hasExtension(preAlertFile, EXCEL_EXTENSIONS)) {
      return "Upload Pre Alert File must be an Excel file";
    }
    if (preAlertFile.size > EXCEL_MAX_BYTES) {
      return "Upload Pre Alert File must be smaller than 20 MB";
    }
    return null;
  }, [airWaybillDocuments, form.airWaybillNumber, form.grossWeightKg, form.pieces, preAlertFile]);

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setNotice(null);

      const validationMessage = validateForm();
      if (validationMessage || !preAlertFile) {
        const message = validationMessage ?? "Upload file is required";
        setNotice({ tone: "error", text: message });
        setUploadErrorDialog({
          title: "上传信息不完整",
          message
        });
        return;
      }

      setIsSubmitting(true);
      try {
        const response = await uploadPreAlertFile({
          shipmentType: form.shipmentType,
          airWaybillNumber: form.airWaybillNumber.trim(),
          grossWeightKg: form.grossWeightKg.trim(),
          pieces: form.pieces.trim(),
          arrivalFlightNumber: form.arrivalFlightNumber.trim() || undefined,
          targetUserId: isAdmin ? form.targetUserId : undefined,
          airWaybillDocuments,
          preAlertFile
        });
        setNotice({
          tone: "success",
          text: `Upload saved for ${response.airWaybillNumber}`
        });
        setForm((current) => ({
          ...initialForm,
          targetUserId: current.targetUserId || currentUser?.id || ""
        }));
        setAirWaybillDocuments([]);
        setPreAlertFile(null);
        await refreshUploads();
      } catch (error) {
        if (isUnauthorizedError(error)) {
          router.replace("/");
          return;
        }
        const message = cleanUploadErrorMessage(error);
        setNotice({
          tone: "error",
          text: message
        });
        setUploadErrorDialog({
          title: uploadErrorTitle(message),
          message
        });
      } finally {
        setIsSubmitting(false);
      }
    },
    [
      airWaybillDocuments,
      currentUser?.id,
      form,
      isAdmin,
      preAlertFile,
      refreshUploads,
      router,
      validateForm
    ]
  );

  const handleReview = useCallback(
    async (uploadId: string, status: WaybillUploadStatus) => {
      try {
        await updateWaybillUploadStatus(uploadId, status);
        setNotice({ tone: "success", text: `Upload marked as ${statusLabel(status)}` });
        await refreshUploads();
      } catch (error) {
        setNotice({
          tone: "error",
          text: error instanceof Error ? error.message : "Unable to update upload"
        });
      }
    },
    [refreshUploads]
  );

  const handleApplyFilters = useCallback(async () => {
    await refreshUploads();
  }, [refreshUploads]);

  const handleResetFilters = useCallback(async () => {
    setFilters(initialFilters);
    await refreshUploads(currentUser, initialFilters);
  }, [currentUser, refreshUploads]);

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
        setNotice({
          tone: "error",
          text: error instanceof Error ? error.message : "Unable to delete upload"
        });
      } finally {
        setDeletingUploadId(null);
      }
    },
    [refreshUploads, router]
  );

  const handleLogout = useCallback(async () => {
    await logout();
    router.replace("/");
  }, [router]);

  if (authState === "loading") {
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
      active="uploads"
      isInfoOpen={false}
      messages={[]}
      onInfoClose={() => undefined}
      onInfoOpen={() => undefined}
      onLogout={handleLogout}
      unreadCount={0}
      user={currentUser}
    >
      <section className={styles.workspace}>
        <div className={styles.workspaceHeader}>
          <div>
            <p className={styles.eyebrow}>Waybills</p>
            <h2>Upload Pre Alert</h2>
          </div>
          <span className={styles.accountTag}>
            {isAdmin ? "Admin review enabled" : currentUser.email}
          </span>
        </div>

        <form className={styles.uploadWindow} noValidate onSubmit={handleSubmit}>
          <div className={styles.windowTitle}>
            <UploadCloud aria-hidden="true" size={22} />
            <div>
              <strong>Pre Alert Upload</strong>
              <span>{selectedOwner ? `Owner: ${selectedOwner.email}` : "Owner: current account"}</span>
            </div>
          </div>

          <div className={styles.formGrid}>
            <fieldset className={styles.radioGroup}>
              <legend>Shipment Type</legend>
              {(["Air", "Road", "Train"] as ShipmentType[]).map((option) => (
                <label key={option}>
                  <input
                    checked={form.shipmentType === option}
                    name="shipmentType"
                    onChange={() => setForm((current) => ({ ...current, shipmentType: option }))}
                    type="radio"
                  />
                  {option}
                </label>
              ))}
            </fieldset>

            {isAdmin && (
              <label className={styles.field}>
                Target User
                <select
                  onChange={(event) =>
                    setForm((current) => ({ ...current, targetUserId: event.target.value }))
                  }
                  value={form.targetUserId}
                >
                  {users.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.email}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <label className={styles.field}>
              Air Waybill Number
              <input
                onChange={(event) =>
                  setForm((current) => ({ ...current, airWaybillNumber: event.target.value }))
                }
                placeholder="784-84063276"
                required
                value={form.airWaybillNumber}
              />
            </label>

            <label className={styles.field}>
              Air Waybill Gross Weight (KG)
              <input
                inputMode="decimal"
                onChange={(event) =>
                  setForm((current) => ({ ...current, grossWeightKg: event.target.value }))
                }
                placeholder="1027.5"
                required
                value={form.grossWeightKg}
              />
            </label>

            <label className={styles.field}>
              Air Waybill Pieces
              <input
                inputMode="numeric"
                onChange={(event) =>
                  setForm((current) => ({ ...current, pieces: event.target.value }))
                }
                placeholder="78"
                required
                value={form.pieces}
              />
            </label>

            <label className={styles.field}>
              Arrival Flight Number
              <input
                onChange={(event) =>
                  setForm((current) => ({ ...current, arrivalFlightNumber: event.target.value }))
                }
                placeholder="EK0147"
                value={form.arrivalFlightNumber}
              />
            </label>
          </div>

          <div className={styles.fileGrid}>
            <label className={styles.fileDrop}>
              <FileText aria-hidden="true" size={24} />
              <strong>Air Waybill Document(s)</strong>
              <span>PDF only, each file under 10 MB</span>
              <input
                aria-label="Air Waybill Document(s)"
                accept="application/pdf,.pdf"
                multiple
                onChange={(event) =>
                  setAirWaybillDocuments(Array.from(event.target.files ?? []))
                }
                required
                type="file"
              />
              <small>
                {airWaybillDocuments.length
                  ? airWaybillDocuments
                      .map((file) => `${file.name} (${formatBytes(file.size)})`)
                      .join("; ")
                  : "No PDF selected"}
              </small>
            </label>

            <label className={styles.fileDrop}>
              <FileSpreadsheet aria-hidden="true" size={24} />
              <strong>Upload Pre Alert File</strong>
              <span>Upload Customer Pre Alert</span>
              <input
                aria-label="Upload Pre Alert File"
                accept=".xls,.xlsx"
                onChange={(event) => setPreAlertFile(event.target.files?.[0] ?? null)}
                required
                type="file"
              />
              <small>
                {preAlertFile
                  ? `${preAlertFile.name} (${formatBytes(preAlertFile.size)})`
                  : "No Excel file selected"}
              </small>
            </label>
          </div>

          <div className={styles.formFooter}>
            {notice && (
              <div className={styles.notice} data-tone={notice.tone} role={notice.tone === "error" ? "alert" : "status"}>
                {notice.text}
              </div>
            )}
            <button disabled={isSubmitting} type="submit">
              {isSubmitting ? "Uploading..." : "Upload Pre Alert"}
            </button>
          </div>
        </form>

        {uploadErrorDialog && (
          <div className={styles.dialogBackdrop} role="presentation">
            <section
              aria-labelledby="upload-error-title"
              aria-modal="true"
              className={styles.errorDialog}
              role="dialog"
            >
              <div className={styles.dialogHeader}>
                <span className={styles.dialogIcon}>
                  <AlertTriangle aria-hidden="true" size={22} />
                </span>
                <div>
                  <p className={styles.eyebrow}>Upload validation</p>
                  <h3 id="upload-error-title">{uploadErrorDialog.title}</h3>
                </div>
                <button
                  aria-label="Close upload error"
                  className={styles.dialogClose}
                  onClick={() => setUploadErrorDialog(null)}
                  type="button"
                >
                  <X aria-hidden="true" size={18} />
                </button>
              </div>
              <p className={styles.dialogMessage}>{uploadErrorDialog.message}</p>
              <div className={styles.dialogFooter}>
                <button onClick={() => setUploadErrorDialog(null)} type="button">
                  我知道了
                </button>
              </div>
            </section>
          </div>
        )}

        <section className={styles.uploadList}>
          <div className={styles.listHeader}>
            <div>
              <p className={styles.eyebrow}>{isAdmin ? "Review queue" : "My uploads"}</p>
              <h3>{isAdmin ? "All Pre Alerts" : "Uploaded Waybills"}</h3>
            </div>
            <button disabled={isLoadingUploads} onClick={() => void refreshUploads()} type="button">
              Refresh
            </button>
          </div>

          {isAdmin && (
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
          )}

          {uploads.length ? (
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Number</th>
                    <th>Type</th>
                    <th>Owner</th>
                    <th>Weight</th>
                    <th>Pieces</th>
                    <th>Flight</th>
                    <th>Status</th>
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
                        <td>{upload.user?.email ?? "-"}</td>
                        <td>{upload.grossWeightKg}</td>
                        <td>{upload.pieces}</td>
                        <td>{upload.arrivalFlightNumber || "-"}</td>
                        <td>
                          <span className={styles.statusPill} data-status={upload.status}>
                            {statusLabel(upload.status)}
                          </span>
                        </td>
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
                            </button>
                            {isAdmin && (
                              <>
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
                              </>
                            )}
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
                          <td colSpan={10}>
                            <div className={styles.detailPanel}>
                              <div className={styles.detailGrid}>
                                <div>
                                  <span>Owner</span>
                                  <strong>{upload.user?.email ?? upload.userId}</strong>
                                </div>
                                <div>
                                  <span>Uploaded At</span>
                                  <strong>{formatDateTime(upload.createdAt)}</strong>
                                </div>
                              </div>

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
              {isLoadingUploads ? "Loading uploads..." : "No uploads yet"}
            </div>
          )}
        </section>
      </section>
    </AppShell>
  );
}

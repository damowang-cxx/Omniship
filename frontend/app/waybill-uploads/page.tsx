"use client";

import { Fragment, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Download,
  Eye,
  FileSpreadsheet,
  FileText,
  ReceiptEuro,
  Trash2,
  UploadCloud,
  WalletCards,
  X
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import {
  deleteWaybillUpload,
  estimatePreAlertTax,
  getCurrentUser,
  getWaybillUploadFileDownloadUrl,
  isUnauthorizedError,
  listUsers,
  listSuppliers,
  listWaybillUploads,
  logout,
  uploadPreAlertFile
} from "@/lib/api";
import type {
  AppUser,
  BillingTaxEstimateResponse,
  ShipmentType,
  SupplierItem,
  WaybillUploadItem
} from "@/lib/types";
import styles from "./page.module.css";

const PDF_MAX_BYTES = 10 * 1024 * 1024;

const initialForm = {
  shipmentType: "Air" as ShipmentType,
  airWaybillNumber: "",
  grossWeightKg: "",
  pieces: "",
  arrivalFlightNumber: "",
  airportOfDeparture: "",
  airportOfArrival: "",
  targetUserId: "",
  supplierId: ""
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

function formatEuro(value: string | undefined) {
  return new Intl.NumberFormat("en-IE", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2
  }).format(Number(value || 0));
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

function statusLabel(status: WaybillUploadItem["status"]) {
  const labels: Record<WaybillUploadItem["status"], string> = {
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
    ? "Excel validation failed"
    : "Upload failed";
}

export default function WaybillUploadsPage() {
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<AppUser | null>(null);
  const [authState, setAuthState] = useState<"loading" | "ready">("loading");
  const [authError, setAuthError] = useState<string | null>(null);
  const [users, setUsers] = useState<AppUser[]>([]);
  const [suppliers, setSuppliers] = useState<SupplierItem[]>([]);
  const [uploads, setUploads] = useState<WaybillUploadItem[]>([]);
  const [form, setForm] = useState(initialForm);
  const [airWaybillDocuments, setAirWaybillDocuments] = useState<File[]>([]);
  const [preAlertFile, setPreAlertFile] = useState<File | null>(null);
  const [taxEstimate, setTaxEstimate] = useState<BillingTaxEstimateResponse | null>(null);
  const [taxEstimateError, setTaxEstimateError] = useState<string | null>(null);
  const [isEstimatingTax, setIsEstimatingTax] = useState(false);
  const estimateRequestId = useRef(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingUploads, setIsLoadingUploads] = useState(false);
  const [deletingUploadId, setDeletingUploadId] = useState<string | null>(null);
  const [expandedUploadId, setExpandedUploadId] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [uploadErrorDialog, setUploadErrorDialog] = useState<{
    title: string;
    message: string;
  } | null>(null);

  const isAdmin = currentUser?.role === "admin";

  const refreshOwnUploads = useCallback(async (actorOverride?: AppUser | null) => {
    const actor = actorOverride ?? currentUser;
    if (!actor || actor.role === "admin") {
      return;
    }
    setIsLoadingUploads(true);
    try {
      const response = await listWaybillUploads({});
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
  }, [currentUser, router]);

  useEffect(() => {
    async function loadCurrentUser() {
      try {
        const response = await getCurrentUser();
        setCurrentUser(response.user);
        setForm((current) => ({ ...current, targetUserId: response.user.id }));

        const suppliersResponse = await listSuppliers();
        setSuppliers(suppliersResponse.items);
        setForm((current) => ({
          ...current,
          supplierId: suppliersResponse.items[0]?.id ?? ""
        }));

        if (response.user.role === "admin") {
          const usersResponse = await listUsers();
          const activeUsers = usersResponse.items.filter((user) => user.status === "active");
          setUsers(activeUsers);
          setForm((current) => ({
            ...current,
            targetUserId: activeUsers[0]?.id ?? response.user.id
          }));
        } else {
          const uploadsResponse = await listWaybillUploads({});
          setUploads(uploadsResponse.items);
        }
      } catch (error) {
        setAuthError(
          error instanceof Error ? error.message : "Unable to load account information"
        );
        router.replace("/");
      } finally {
        setAuthState("ready");
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

  const selectedSupplier = useMemo(
    () => suppliers.find((supplier) => supplier.id === form.supplierId) ?? null,
    [form.supplierId, suppliers]
  );

  const handlePreAlertFileChange = useCallback((file: File | null) => {
    setPreAlertFile(file);
    setTaxEstimate(null);
    setTaxEstimateError(null);
  }, []);

  useEffect(() => {
    if (
      !preAlertFile ||
      !form.supplierId ||
      !/^[A-Za-z]{3}$/.test(form.airportOfArrival.trim())
    ) {
      setIsEstimatingTax(false);
      return;
    }
    const requestId = ++estimateRequestId.current;
    setIsEstimatingTax(true);
    setTaxEstimateError(null);
    void estimatePreAlertTax(
      preAlertFile,
      form.supplierId,
      form.airportOfArrival.trim().toUpperCase()
    )
      .then((estimate) => {
        if (requestId === estimateRequestId.current) {
          setTaxEstimate(estimate);
        }
      })
      .catch((error) => {
        if (requestId === estimateRequestId.current) {
          setTaxEstimate(null);
          setTaxEstimateError(cleanUploadErrorMessage(error));
        }
      })
      .finally(() => {
        if (requestId === estimateRequestId.current) {
          setIsEstimatingTax(false);
        }
      });
  }, [form.airportOfArrival, form.supplierId, preAlertFile]);

  const validateForm = useCallback(() => {
    if (!form.airWaybillNumber.trim()) {
      return "Air Waybill Number is required";
    }
    if (!form.supplierId) {
      return "Supplier is required";
    }
    if (!form.grossWeightKg.trim() || !Number.isFinite(Number(form.grossWeightKg))) {
      return "Air Waybill Gross Weight (KG) must be a number";
    }
    if (!form.pieces.trim() || !/^\d+$/.test(form.pieces.trim())) {
      return "Air Waybill Pieces must be a number";
    }
    if (!form.airportOfDeparture.trim()) {
      return "Airport of Departure is required";
    }
    if (!/^[A-Za-z]{3}$/.test(form.airportOfArrival.trim())) {
      return "Airport of Arrival must be a three-letter IATA code";
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
    if (!hasExtension(preAlertFile, [".xls", ".xlsx"])) {
      return "Upload Pre Alert File must be an XLS or XLSX workbook";
    }
    return null;
  }, [
    airWaybillDocuments,
    form.airWaybillNumber,
    form.airportOfArrival,
    form.airportOfDeparture,
    form.grossWeightKg,
    form.pieces,
    form.supplierId,
    preAlertFile
  ]);

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setNotice(null);

      const validationMessage = validateForm();
      if (validationMessage || !preAlertFile) {
        const message = validationMessage ?? "Upload file is required";
        setNotice({ tone: "error", text: message });
        setUploadErrorDialog({
          title: "Upload information is incomplete",
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
          airportOfDeparture: form.airportOfDeparture.trim(),
          airportOfArrival: form.airportOfArrival.trim(),
          targetUserId: isAdmin ? form.targetUserId : undefined,
          supplierId: form.supplierId,
          airWaybillDocuments,
          preAlertFile
        });
        setNotice({
          tone: "success",
          text: `Upload saved for ${response.airWaybillNumber}. Tax deducted: ${formatEuro(response.deductedTax)}`
        });
        if (isAdmin) {
          setUsers((current) => current.map((user) =>
            user.id === response.boundUserId
              ? { ...user, balance: response.balanceAfter }
              : user
          ));
        } else {
          setCurrentUser((current) => current ? { ...current, balance: response.balanceAfter } : current);
        }
        setForm((current) => ({
          ...initialForm,
          targetUserId: current.targetUserId || currentUser?.id || "",
          supplierId: current.supplierId
        }));
        setAirWaybillDocuments([]);
        setPreAlertFile(null);
        setTaxEstimate(null);
        setTaxEstimateError(null);
        await refreshOwnUploads();
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
      refreshOwnUploads,
      router,
      validateForm
    ]
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
        await refreshOwnUploads();
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
    [refreshOwnUploads, router]
  );

  const handleLogout = useCallback(async () => {
    await logout();
    router.replace("/");
  }, [router]);

  if (authState === "loading") {
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
            {isAdmin ? "Admin upload mode" : currentUser.email}
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

            <label className={styles.field}>
              Supplier
              <select
                aria-label="Supplier"
                onChange={(event) =>
                  setForm((current) => ({ ...current, supplierId: event.target.value }))
                }
                required
                value={form.supplierId}
              >
                <option value="">Select supplier</option>
                {suppliers.map((supplier) => (
                  <option key={supplier.id} value={supplier.id}>
                    {supplier.name} · v{supplier.currentVersionNumber}
                  </option>
                ))}
              </select>
            </label>

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

          <div className={styles.routeGrid}>
            <label className={styles.field}>
              Airport of Departure
              <input
                maxLength={120}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    airportOfDeparture: event.target.value
                  }))
                }
                placeholder="HKG"
                required
                value={form.airportOfDeparture}
              />
            </label>

            <label className={styles.field}>
              Airport of Arrival
              <input
                autoCapitalize="characters"
                maxLength={3}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    airportOfArrival: event.target.value.toUpperCase().slice(0, 3)
                  }))
                }
                placeholder="AMS"
                required
                value={form.airportOfArrival}
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
              <span>XLS or XLSX · validated with {selectedSupplier?.name || "supplier"} rules</span>
              <input
                aria-label="Upload Pre Alert File"
                accept=".xls,.xlsx,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={(event) => void handlePreAlertFileChange(event.target.files?.[0] ?? null)}
                required
                type="file"
              />
              <small>
                {preAlertFile
                  ? `${preAlertFile.name} (${formatBytes(preAlertFile.size)})`
                  : "No file selected"}
              </small>
            </label>
          </div>

          <div className={styles.formFooter}>
            {notice && (
              <div className={styles.notice} data-tone={notice.tone} role={notice.tone === "error" ? "alert" : "status"}>
                {notice.text}
              </div>
            )}
            <div className={styles.billingFooter}>
              <button disabled={isSubmitting} type="submit">
                {isSubmitting ? "Uploading..." : "Upload Pre Alert"}
              </button>
              <div className={styles.accountSnapshot}>
                <WalletCards aria-hidden="true" size={20} />
                <div><span>Customer balance</span><strong>{formatEuro(selectedOwner?.balance)}</strong></div>
              </div>
              <div className={styles.taxSnapshot} data-state={taxEstimateError ? "error" : taxEstimate ? "ready" : "idle"}>
                <ReceiptEuro aria-hidden="true" size={20} />
                <div>
                  <span>Tax for this upload</span>
                  <strong>{isEstimatingTax ? "Calculating..." : taxEstimate ? formatEuro(taxEstimate.estimatedTax) : taxEstimateError ? "Unavailable" : "Select Pre Alert"}</strong>
                  {taxEstimate && <small>{taxEstimate.billableUnitCount} unique units × {formatEuro(taxEstimate.unitRate)}{taxEstimate.taxableAirport ? "" : " · non-taxable airport"}</small>}
                  {taxEstimateError && <small title={taxEstimateError}>The file could not be estimated</small>}
                </div>
              </div>
            </div>
            {taxEstimate && taxEstimate.warningCount > 0 && (
              <div className={styles.validationWarning} role="status">
                <AlertTriangle aria-hidden="true" size={18} />
                <div>
                  <strong>{taxEstimate.warningCount} non-blocking supplier rule warnings</strong>
                  {taxEstimate.warnings.slice(0, 3).map((warning) => (
                    <span key={`${warning.ruleKey}-${warning.rowNumber}-${warning.message}`}>
                      Row {warning.rowNumber}, {warning.ruleName}: {warning.message}
                    </span>
                  ))}
                </div>
              </div>
            )}
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
                  I understand
                </button>
              </div>
            </section>
          </div>
        )}

        {isAdmin ? (
          <section className={styles.uploadList}>
            <div className={styles.listHeader}>
              <div>
                <p className={styles.eyebrow}>Admin queue</p>
                <h3>Manage submitted waybills</h3>
              </div>
              <button onClick={() => router.push("/waybill-upload-management")} type="button">
                Open management
              </button>
            </div>
            <div className={styles.emptyState}>
              Admin review, downloads, filters, and deletion are handled on the management page.
            </div>
          </section>
        ) : (
          <section className={styles.uploadList}>
            <div className={styles.listHeader}>
              <div>
                <p className={styles.eyebrow}>My uploads</p>
                <h3>Uploaded Waybills</h3>
              </div>
              <button disabled={isLoadingUploads} onClick={() => void refreshOwnUploads()} type="button">
                Refresh
              </button>
            </div>

            {uploads.length ? (
              <div className={styles.tableWrap}>
                <table>
                  <thead>
                    <tr>
                      <th>Number</th>
                      <th>Type</th>
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
                            <td colSpan={11}>
                              <div className={styles.detailPanel}>
                                <div className={styles.detailGrid}>
                                  <div>
                                    <span>Owner</span>
                                    <strong>{currentUser.email}</strong>
                                  </div>
                                  <div>
                                    <span>Departure</span>
                                    <strong>{upload.airportOfDeparture || "-"}</strong>
                                  </div>
                                  <div>
                                    <span>Arrival</span>
                                    <strong>{upload.airportOfArrival || "-"}</strong>
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
        )}
      </section>
    </AppShell>
  );
}

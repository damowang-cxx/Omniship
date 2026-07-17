"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { CheckCircle2, CircleSlash } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { AppMessage } from "@/components/InfoCenter";
import {
  deleteWaybillPodFile,
  getCurrentUser,
  getWaybillPodFileDownloadUrl,
  getWaybill,
  isUnauthorizedError,
  listWaybillParcels,
  logout,
  updateWaybillParcels,
  uploadWaybillPodFile,
  updateWaybill
} from "@/lib/api";
import type {
  AppUser,
  WaybillItem,
  WaybillParcelBulkUpdatePayload,
  WaybillParcelItem,
  WaybillParcelStatus,
  WaybillPodFileItem
} from "@/lib/types";
import styles from "../page.module.css";

type MilestoneKey =
  | "noaAt"
  | "collectionAt"
  | "scannedAt"
  | "customsClearanceAt"
  | "outboundAt";

const milestoneFields: {
  key: MilestoneKey;
  label: string;
  helper: string;
  inputLabel: string;
}[] = [
  { key: "noaAt", label: "NOA", helper: "NOA时间", inputLabel: "NOA Time" },
  {
    key: "collectionAt",
    label: "Collection",
    helper: "提货时间",
    inputLabel: "Collection Time"
  },
  { key: "scannedAt", label: "Scanned", helper: "扫描入仓时间", inputLabel: "Scanned Time" },
  {
    key: "customsClearanceAt",
    label: "Customs Clearance",
    helper: "清关完成时间",
    inputLabel: "Customs Clearance Time"
  },
  { key: "outboundAt", label: "Outbound", helper: "出库时间", inputLabel: "Outbound Time" }
];

const emptyMilestoneForm: Record<MilestoneKey, string> = {
  noaAt: "",
  collectionAt: "",
  scannedAt: "",
  customsClearanceAt: "",
  outboundAt: ""
};

const parcelStatusOptions: { value: WaybillParcelStatus; label: string }[] = [
  { value: "created", label: "Created" },
  { value: "pending_check", label: "Pending Check" },
  { value: "inspection", label: "Inspection" },
  { value: "released", label: "Released" },
  { value: "temporary_released", label: "Temporary Released" },
  { value: "exception", label: "Exception" },
  { value: "confiscated", label: "Confiscated" },
  { value: "destroyed", label: "Destroyed" },
  { value: "on_hold", label: "On Hold" },
  { value: "inbound", label: "Inbound" },
  { value: "outbound", label: "Outbound" }
];

type BulkFlagValue = "" | "true" | "false";

type BulkParcelForm = {
  status: WaybillParcelStatus | "";
  inbound: BulkFlagValue;
  outbound: BulkFlagValue;
  specialInstruction: BulkFlagValue;
};

const emptyBulkParcelForm: BulkParcelForm = {
  status: "",
  inbound: "",
  outbound: "",
  specialInstruction: ""
};

const parcelFlagLabels = {
  inbound: "Inbound",
  outbound: "Outbound",
  specialInstruction: "Special Instruction"
} as const;

function formatMilestoneTime(value?: string | null) {
  if (!value) {
    return "Not set";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    year: "numeric"
  }).format(date);
}

function toDateTimeLocalValue(value?: string | null) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return localDate.toISOString().slice(0, 16);
}

function fromDateTimeLocalValue(value: string) {
  return value ? new Date(value).toISOString() : null;
}

function formatFileSize(sizeBytes: number) {
  if (sizeBytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(sizeBytes / 1024))} KB`;
  }
  return `${(sizeBytes / 1024 / 1024).toFixed(2)} MB`;
}

function parcelStatusLabel(status: WaybillParcelStatus) {
  return parcelStatusOptions.find((option) => option.value === status)?.label ?? status;
}

function formatFlagEmoji(countryCode?: string | null) {
  const normalized = countryCode?.trim().toUpperCase();
  if (!normalized || normalized.length !== 2) {
    return "";
  }
  return normalized
    .split("")
    .map((letter) => String.fromCodePoint(127397 + letter.charCodeAt(0)))
    .join("");
}

function destinationLabel(parcel: WaybillParcelItem) {
  return parcel.destinationName || parcel.destinationRaw || "Unknown";
}

function bulkFlagToBoolean(value: BulkFlagValue) {
  if (value === "true") {
    return true;
  }
  if (value === "false") {
    return false;
  }
  return undefined;
}

function buildMilestoneForm(waybill: WaybillItem): Record<MilestoneKey, string> {
  return {
    noaAt: toDateTimeLocalValue(waybill.noaAt),
    collectionAt: toDateTimeLocalValue(waybill.collectionAt),
    scannedAt: toDateTimeLocalValue(waybill.scannedAt),
    customsClearanceAt: toDateTimeLocalValue(waybill.customsClearanceAt),
    outboundAt: toDateTimeLocalValue(waybill.outboundAt)
  };
}

export default function WaybillDetailPage() {
  const params = useParams<{ publicCode: string }>();
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<AppUser | null>(null);
  const [waybill, setWaybill] = useState<WaybillItem | null>(null);
  const [parcels, setParcels] = useState<WaybillParcelItem[]>([]);
  const [authError, setAuthError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [messages, setMessages] = useState<AppMessage[]>([]);
  const [isInfoOpen, setIsInfoOpen] = useState(false);
  const [milestoneForm, setMilestoneForm] =
    useState<Record<MilestoneKey, string>>(emptyMilestoneForm);
  const [isSavingMilestones, setIsSavingMilestones] = useState(false);
  const [podFile, setPodFile] = useState<File | null>(null);
  const [isUploadingPod, setIsUploadingPod] = useState(false);
  const [deletingPodFileId, setDeletingPodFileId] = useState<string | null>(null);
  const [selectedParcelIds, setSelectedParcelIds] = useState<Set<string>>(new Set());
  const [bulkParcelForm, setBulkParcelForm] =
    useState<BulkParcelForm>(emptyBulkParcelForm);
  const [isSavingParcels, setIsSavingParcels] = useState(false);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(
    null
  );

  const isAdmin = currentUser?.role === "admin";
  const podFiles = waybill?.podFiles ?? [];
  const canUploadPod = isAdmin && podFiles.length < 2;
  const allParcelsSelected = parcels.length > 0 && selectedParcelIds.size === parcels.length;

  const addMessage = useCallback((title: string, body: string, tone: "error" | "info") => {
    setMessages((current) => [
      {
        id: `${Date.now()}-${current.length}`,
        title,
        body,
        tone,
        createdAt: new Date().toISOString(),
        read: false
      },
      ...current
    ]);
  }, []);

  useEffect(() => {
    async function bootstrap() {
      try {
        const [userResult, waybillResult, parcelResult] = await Promise.allSettled([
          getCurrentUser(),
          getWaybill(params.publicCode),
          listWaybillParcels(params.publicCode)
        ]);
        if (userResult.status === "rejected") {
          throw userResult.reason;
        }
        if (waybillResult.status === "rejected") {
          throw waybillResult.reason;
        }

        setCurrentUser(userResult.value.user);
        setWaybill(waybillResult.value);
        setMilestoneForm(buildMilestoneForm(waybillResult.value));

        if (parcelResult.status === "fulfilled") {
          setParcels(parcelResult.value.items);
        } else {
          if (isUnauthorizedError(parcelResult.reason)) {
            throw parcelResult.reason;
          }
          const message =
            parcelResult.reason instanceof Error
              ? parcelResult.reason.message
              : "Unable to load parcel details";
          setParcels([]);
          setNotice({
            tone: "error",
            text: `Waybill loaded without parcel details. ${message}`
          });
          addMessage("Parcel details unavailable", message, "error");
        }
      } catch (error) {
        if (isUnauthorizedError(error)) {
          router.replace("/");
          return;
        }
        setAuthError(error instanceof Error ? error.message : "Unable to load waybill");
      } finally {
        setIsLoading(false);
      }
    }

    void bootstrap();
  }, [addMessage, params.publicCode, router]);

  const handleLogout = useCallback(async () => {
    await logout();
    router.replace("/");
  }, [router]);

  const handleSaveMilestones = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!waybill || !isAdmin) {
        return;
      }

      setIsSavingMilestones(true);
      setNotice(null);
      try {
        const updated = await updateWaybill(waybill.publicCode, {
          noaAt: fromDateTimeLocalValue(milestoneForm.noaAt),
          collectionAt: fromDateTimeLocalValue(milestoneForm.collectionAt),
          scannedAt: fromDateTimeLocalValue(milestoneForm.scannedAt),
          customsClearanceAt: fromDateTimeLocalValue(milestoneForm.customsClearanceAt),
          outboundAt: fromDateTimeLocalValue(milestoneForm.outboundAt)
        });
        setWaybill(updated);
        setMilestoneForm(buildMilestoneForm(updated));
        setNotice({ tone: "success", text: "Waybill milestone times updated" });
        addMessage(
          "Waybill updated",
          `${updated.number} milestone times were updated.`,
          "info"
        );
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Unable to update milestone times";
        setNotice({ tone: "error", text: message });
        addMessage("Waybill update failed", message, "error");
      } finally {
        setIsSavingMilestones(false);
      }
    },
    [addMessage, isAdmin, milestoneForm, waybill]
  );

  const handleUploadPod = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!waybill || !canUploadPod || !podFile) {
        return;
      }

      const form = event.currentTarget;
      setIsUploadingPod(true);
      setNotice(null);
      try {
        const updated = await uploadWaybillPodFile(waybill.publicCode, podFile);
        setWaybill(updated);
        setPodFile(null);
        form.reset();
        setNotice({ tone: "success", text: "POD file uploaded" });
        addMessage(
          "POD uploaded",
          `${podFile.name} was added to ${updated.number}.`,
          "info"
        );
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to upload POD";
        setNotice({ tone: "error", text: message });
        addMessage("POD upload failed", message, "error");
      } finally {
        setIsUploadingPod(false);
      }
    },
    [addMessage, canUploadPod, podFile, waybill]
  );

  const handleDeletePod = useCallback(
    async (file: WaybillPodFileItem) => {
      if (!waybill || !isAdmin) {
        return;
      }
      if (
        typeof window !== "undefined" &&
        !window.confirm(`Delete POD file "${file.originalFilename}"?`)
      ) {
        return;
      }

      setDeletingPodFileId(file.id);
      setNotice(null);
      try {
        const deleted = await deleteWaybillPodFile(waybill.publicCode, file.id);
        setWaybill((current) =>
          current
            ? {
                ...current,
                podFiles: current.podFiles.filter(
                  (podItem) => podItem.id !== deleted.podFileId
                )
              }
            : current
        );
        setNotice({ tone: "success", text: "POD file deleted" });
        addMessage(
          "POD deleted",
          `${file.originalFilename} was removed from ${waybill.number}.`,
          "info"
        );
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to delete POD";
        setNotice({ tone: "error", text: message });
        addMessage("POD delete failed", message, "error");
      } finally {
        setDeletingPodFileId(null);
      }
    },
    [addMessage, isAdmin, waybill]
  );

  const handleSelectParcel = useCallback((parcelId: string, isSelected: boolean) => {
    setSelectedParcelIds((current) => {
      const next = new Set(current);
      if (isSelected) {
        next.add(parcelId);
      } else {
        next.delete(parcelId);
      }
      return next;
    });
  }, []);

  const handleSelectAllParcels = useCallback(
    (isSelected: boolean) => {
      setSelectedParcelIds(isSelected ? new Set(parcels.map((parcel) => parcel.id)) : new Set());
    },
    [parcels]
  );

  const applyParcelUpdate = useCallback(
    async (
      parcelIds: string[],
      changes: Omit<WaybillParcelBulkUpdatePayload, "parcelIds">,
      successText: string
    ) => {
      if (!waybill || !isAdmin || parcelIds.length === 0) {
        return;
      }

      setIsSavingParcels(true);
      setNotice(null);
      try {
        const updated = await updateWaybillParcels(waybill.publicCode, {
          parcelIds,
          ...changes
        });
        setParcels(updated.items);
        setSelectedParcelIds((current) => {
          const updatedIds = new Set(updated.items.map((parcel) => parcel.id));
          return new Set(Array.from(current).filter((parcelId) => updatedIds.has(parcelId)));
        });
        setNotice({ tone: "success", text: successText });
        addMessage("Parcels updated", successText, "info");
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to update parcels";
        setNotice({ tone: "error", text: message });
        addMessage("Parcel update failed", message, "error");
      } finally {
        setIsSavingParcels(false);
      }
    },
    [addMessage, isAdmin, waybill]
  );

  const handleParcelStatusChange = useCallback(
    (parcel: WaybillParcelItem, status: WaybillParcelStatus) =>
      applyParcelUpdate([parcel.id], { status }, `${parcel.parcelUnitNumber} status updated`),
    [applyParcelUpdate]
  );

  const handleParcelFlagChange = useCallback(
    (
      parcel: WaybillParcelItem,
      field: "inbound" | "outbound" | "specialInstruction",
      value: boolean
    ) =>
      applyParcelUpdate(
        [parcel.id],
        { [field]: value },
        `${parcel.parcelUnitNumber} parcel flag updated`
      ),
    [applyParcelUpdate]
  );

  const handleBulkParcelUpdate = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const parcelIds = Array.from(selectedParcelIds);
      const changes: Omit<WaybillParcelBulkUpdatePayload, "parcelIds"> = {};
      if (bulkParcelForm.status) {
        changes.status = bulkParcelForm.status;
      }
      const inbound = bulkFlagToBoolean(bulkParcelForm.inbound);
      const outbound = bulkFlagToBoolean(bulkParcelForm.outbound);
      const specialInstruction = bulkFlagToBoolean(bulkParcelForm.specialInstruction);
      if (inbound !== undefined) {
        changes.inbound = inbound;
      }
      if (outbound !== undefined) {
        changes.outbound = outbound;
      }
      if (specialInstruction !== undefined) {
        changes.specialInstruction = specialInstruction;
      }

      if (Object.keys(changes).length === 0) {
        setNotice({ tone: "error", text: "Choose at least one parcel field to update" });
        return;
      }

      await applyParcelUpdate(
        parcelIds,
        changes,
        `${parcelIds.length} parcel${parcelIds.length === 1 ? "" : "s"} updated`
      );
      setBulkParcelForm(emptyBulkParcelForm);
    },
    [applyParcelUpdate, bulkParcelForm, selectedParcelIds]
  );

  const unreadCount = useMemo(
    () => messages.filter((message) => !message.read).length,
    [messages]
  );

  if (isLoading) {
    return <main className={styles.loadingPage}>Loading waybill...</main>;
  }

  if (authError || !currentUser || !waybill) {
    return (
      <main className={styles.loadingPage}>
        <p>{authError ?? "Waybill unavailable"}</p>
        <button onClick={() => router.replace("/waybills")} type="button">
          Return to Waybills
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
        <Link className={styles.backLink} href="/waybills">
          Back to Waybills
        </Link>
        <section className={styles.detailPanel}>
          <div className={styles.detailHeader}>
            <div>
              <p className={styles.eyebrow}>Waybill detail</p>
              <h2>{waybill.number}</h2>
            </div>
            <span className={styles.accountTag}>
              {isAdmin ? "Editable milestones" : "Read-only milestones"}
            </span>
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

          <section className={styles.detailSection}>
            <div className={styles.sectionHeader}>
              <div>
                <p className={styles.eyebrow}>Details</p>
                <h3>Details</h3>
              </div>
            </div>

            <form className={styles.milestoneForm} onSubmit={handleSaveMilestones}>
            <div className={styles.milestoneGrid}>
              {milestoneFields.map((field) => (
                <label className={styles.milestoneItem} key={field.key}>
                  <span className={styles.milestoneLabel}>
                    {field.label}
                    <small>{field.helper}</small>
                  </span>
                  {isAdmin ? (
                    <input
                      aria-label={field.inputLabel}
                      className={styles.milestoneInput}
                      onChange={(event) =>
                        setMilestoneForm((current) => ({
                          ...current,
                          [field.key]: event.target.value
                        }))
                      }
                      type="datetime-local"
                      value={milestoneForm[field.key]}
                    />
                  ) : (
                    <span
                      className={styles.milestoneTime}
                      data-empty={waybill[field.key] ? "false" : "true"}
                    >
                      {formatMilestoneTime(waybill[field.key])}
                    </span>
                  )}
                </label>
              ))}
            </div>

            {isAdmin && (
              <div className={styles.detailActions}>
                <button
                  disabled={isSavingMilestones}
                  onClick={() => setMilestoneForm(buildMilestoneForm(waybill))}
                  type="button"
                >
                  Reset
                </button>
                <button disabled={isSavingMilestones} type="submit">
                  {isSavingMilestones ? "Saving..." : "Save milestone times"}
                </button>
              </div>
            )}
          </form>

          <section className={styles.podSection}>
            <div className={styles.podHeader}>
              <div>
                <p className={styles.eyebrow}>POD</p>
                <h3>签收证明</h3>
              </div>
              <span className={styles.podLimit}>{podFiles.length}/2 files</span>
            </div>

            {podFiles.length > 0 ? (
              <div className={styles.podList}>
                {podFiles.map((file) => (
                  <article className={styles.podItem} key={file.id}>
                    <div>
                      <strong>{file.originalFilename}</strong>
                      <span className={styles.podMeta}>
                        {formatFileSize(file.sizeBytes)} - Uploaded{" "}
                        {formatMilestoneTime(file.createdAt)}
                      </span>
                    </div>
                    <div className={styles.podActions}>
                      <a
                        className={styles.podDownload}
                        href={getWaybillPodFileDownloadUrl(waybill.publicCode, file.id)}
                        rel="noreferrer"
                        target="_blank"
                      >
                        Download File
                      </a>
                      {isAdmin && (
                        <button
                          className={styles.podDelete}
                          disabled={deletingPodFileId === file.id}
                          onClick={() => void handleDeletePod(file)}
                          type="button"
                        >
                          {deletingPodFileId === file.id ? "Deleting..." : "Delete"}
                        </button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className={styles.podEmpty}>No POD file has been uploaded.</div>
            )}

            {isAdmin && (
              <form className={styles.podUpload} onSubmit={handleUploadPod}>
                <label>
                  <span>POD file</span>
                  <input
                    accept="application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png"
                    aria-label="POD file"
                    disabled={!canUploadPod || isUploadingPod}
                    onChange={(event) => setPodFile(event.target.files?.[0] ?? null)}
                    type="file"
                  />
                </label>
                <button disabled={!canUploadPod || !podFile || isUploadingPod} type="submit">
                  {isUploadingPod ? "Uploading..." : "Upload POD"}
                </button>
                {!canUploadPod && (
                  <span className={styles.podLimitNote}>POD upload limit reached.</span>
                )}
              </form>
            )}
            </section>
          </section>

          <section className={styles.parcelSection}>
            <div className={styles.sectionHeader}>
              <div>
                <p className={styles.eyebrow}>Parcels</p>
                <h3>Parcels</h3>
              </div>
              <span className={styles.podLimit}>{parcels.length} parcel(s)</span>
            </div>

            {isAdmin && selectedParcelIds.size > 0 && (
              <form className={styles.parcelBulkToolbar} onSubmit={handleBulkParcelUpdate}>
                <strong>{selectedParcelIds.size} selected</strong>
                <label>
                  <span>Status</span>
                  <select
                    aria-label="Bulk parcel status"
                    disabled={isSavingParcels}
                    onChange={(event) =>
                      setBulkParcelForm((current) => ({
                        ...current,
                        status: event.target.value as WaybillParcelStatus | ""
                      }))
                    }
                    value={bulkParcelForm.status}
                  >
                    <option value="">No status change</option>
                    {parcelStatusOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                {(["inbound", "outbound", "specialInstruction"] as const).map((field) => (
                  <label key={field}>
                    <span>{parcelFlagLabels[field]}</span>
                    <select
                      aria-label={`Bulk parcel ${parcelFlagLabels[field]}`}
                      disabled={isSavingParcels}
                      onChange={(event) =>
                        setBulkParcelForm((current) => ({
                          ...current,
                          [field]: event.target.value as BulkFlagValue
                        }))
                      }
                      value={bulkParcelForm[field]}
                    >
                      <option value="">No change</option>
                      <option value="true">Check</option>
                      <option value="false">Cross</option>
                    </select>
                  </label>
                ))}
                <button disabled={isSavingParcels} type="submit">
                  {isSavingParcels ? "Applying..." : "Apply"}
                </button>
                <button
                  disabled={isSavingParcels}
                  onClick={() => setSelectedParcelIds(new Set())}
                  type="button"
                >
                  Clear
                </button>
              </form>
            )}

            {parcels.length > 0 ? (
              <div className={`${styles.tableWrap} ${styles.parcelTableWrap}`}>
                <table className={styles.parcelTable}>
                  <thead>
                    <tr>
                      {isAdmin && (
                        <th>
                          <input
                            aria-label="Select all parcels"
                            checked={allParcelsSelected}
                            className={styles.parcelCheckbox}
                            disabled={isSavingParcels}
                            onChange={(event) =>
                              handleSelectAllParcels(event.currentTarget.checked)
                            }
                            type="checkbox"
                          />
                        </th>
                      )}
                      <th>Parcel Unit Number</th>
                      <th>Status</th>
                      <th>Number Of Items</th>
                      <th>Weight(kg)</th>
                      <th>Destination group</th>
                      <th>Inbound</th>
                      <th>Outbound</th>
                      <th>Special Instruction</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parcels.map((parcel) => (
                      <tr key={parcel.id}>
                        {isAdmin && (
                          <td>
                            <input
                              aria-label={`Select parcel ${parcel.parcelUnitNumber}`}
                              checked={selectedParcelIds.has(parcel.id)}
                              className={styles.parcelCheckbox}
                              disabled={isSavingParcels}
                              onChange={(event) =>
                                handleSelectParcel(parcel.id, event.currentTarget.checked)
                              }
                              type="checkbox"
                            />
                          </td>
                        )}
                        <td>
                          <span className={styles.parcelNumber}>
                            {parcel.parcelUnitNumber}
                          </span>
                        </td>
                        <td>
                          {isAdmin ? (
                            <select
                              aria-label={`Parcel Status ${parcel.parcelUnitNumber}`}
                              className={styles.parcelStatusSelect}
                              disabled={isSavingParcels}
                              onChange={(event) =>
                                void handleParcelStatusChange(
                                  parcel,
                                  event.target.value as WaybillParcelStatus
                                )
                              }
                              value={parcel.status}
                            >
                              {parcelStatusOptions.map((option) => (
                                <option key={option.value} value={option.value}>
                                  {option.label}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <span
                              className={`${styles.statusPill} ${styles.parcelStatusPill}`}
                              data-status={parcel.status}
                            >
                              {parcelStatusLabel(parcel.status)}
                            </span>
                          )}
                        </td>
                        <td>{parcel.numberOfItems ?? "-"}</td>
                        <td>{parcel.weightKg ?? "-"}</td>
                        <td>
                          <span className={styles.parcelDestination}>
                            {formatFlagEmoji(parcel.destinationCode) && (
                              <span aria-hidden="true">
                                {formatFlagEmoji(parcel.destinationCode)}
                              </span>
                            )}
                            <span>{destinationLabel(parcel)}</span>
                          </span>
                        </td>
                        {(["inbound", "outbound", "specialInstruction"] as const).map(
                          (field) => {
                            const value = parcel[field];
                            const label = parcelFlagLabels[field];
                            const dataValue = value ? "true" : "false";
                            const icon = value ? (
                              <CheckCircle2 aria-hidden="true" size={18} />
                            ) : (
                              <CircleSlash aria-hidden="true" size={18} />
                            );

                            return (
                              <td className={styles.parcelBooleanCell} key={field}>
                                {isAdmin ? (
                                  <button
                                    aria-label={`${label} ${parcel.parcelUnitNumber}`}
                                    className={styles.parcelFlagButton}
                                    data-value={dataValue}
                                    disabled={isSavingParcels}
                                    onClick={() =>
                                      void handleParcelFlagChange(parcel, field, !value)
                                    }
                                    type="button"
                                  >
                                    {icon}
                                  </button>
                                ) : (
                                  <span
                                    aria-label={`${label} ${value ? "checked" : "crossed"}`}
                                    className={styles.parcelFlagIcon}
                                    data-value={dataValue}
                                    role="img"
                                  >
                                    {icon}
                                  </span>
                                )}
                              </td>
                            );
                          }
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className={styles.parcelEmpty}>
                No parcels have been parsed from the Pre Alert File.
              </div>
            )}
          </section>
        </section>
      </section>
    </AppShell>
  );
}

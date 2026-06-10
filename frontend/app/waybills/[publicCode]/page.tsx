"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { AppMessage } from "@/components/InfoCenter";
import {
  getCurrentUser,
  getWaybill,
  isUnauthorizedError,
  logout,
  updateWaybill
} from "@/lib/api";
import type { AppUser, WaybillItem } from "@/lib/types";
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
  const [authError, setAuthError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [messages, setMessages] = useState<AppMessage[]>([]);
  const [isInfoOpen, setIsInfoOpen] = useState(false);
  const [milestoneForm, setMilestoneForm] =
    useState<Record<MilestoneKey, string>>(emptyMilestoneForm);
  const [isSavingMilestones, setIsSavingMilestones] = useState(false);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(
    null
  );

  const isAdmin = currentUser?.role === "admin";

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
        const [userResponse, waybillResponse] = await Promise.all([
          getCurrentUser(),
          getWaybill(params.publicCode)
        ]);
        setCurrentUser(userResponse.user);
        setWaybill(waybillResponse);
        setMilestoneForm(buildMilestoneForm(waybillResponse));
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
  }, [params.publicCode, router]);

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
        </section>
      </section>
    </AppShell>
  );
}

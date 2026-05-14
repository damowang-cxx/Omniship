"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { AppMessage } from "@/components/InfoCenter";
import { StatusBadge } from "@/components/StatusBadge";
import { getAirWaybillDetail, getCurrentUser, isUnauthorizedError, logout } from "@/lib/api";
import type { AirWaybillDetailResponse, AppUser } from "@/lib/types";
import styles from "./page.module.css";

type LoadState = "loading" | "ready" | "error";

function ValueRow({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className={styles.valueRow}>
      <span>{label}</span>
      <strong>{value || "-"}</strong>
    </div>
  );
}

export default function AirWaybillDetailPage() {
  const params = useParams<{ number: string }>();
  const router = useRouter();
  const number = useMemo(() => decodeURIComponent(params.number), [params.number]);
  const [currentUser, setCurrentUser] = useState<AppUser | null>(null);
  const [authState, setAuthState] = useState<"loading" | "ready">("loading");
  const [authError, setAuthError] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [data, setData] = useState<AirWaybillDetailResponse | null>(null);
  const [messages, setMessages] = useState<AppMessage[]>([]);
  const [isInfoOpen, setIsInfoOpen] = useState(false);

  const addMessage = useCallback(
    (title: string, body: string, tone: AppMessage["tone"] = "error") => {
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
    },
    []
  );

  useEffect(() => {
    async function load() {
      let userLoaded = false;
      try {
        const me = await getCurrentUser();
        userLoaded = true;
        setCurrentUser(me.user);
        setAuthState("ready");
        const detail = await getAirWaybillDetail(number);
        setData(detail);
        setLoadState("ready");
      } catch (error) {
        if (isUnauthorizedError(error)) {
          setAuthError("登录状态已失效");
          setAuthState("ready");
          router.replace("/login");
          return;
        }
        if (!userLoaded) {
          setAuthError(
            error instanceof Error ? error.message : "无法加载账号信息"
          );
          setAuthState("ready");
          router.replace("/login");
          return;
        }
        setLoadState("error");
        addMessage(
          "详情读取失败",
          error instanceof Error ? error.message : "无法读取 Waybill 详情"
        );
      }
    }

    void load();
  }, [addMessage, number, router]);

  const handleLogout = useCallback(async () => {
    await logout();
    router.replace("/login");
  }, [router]);

  const openInfoCenter = useCallback(() => {
    setIsInfoOpen(true);
    setMessages((current) => current.map((message) => ({ ...message, read: true })));
  }, []);

  if (authState === "loading") {
    return <main className={styles.loadingPage}>正在加载账号信息...</main>;
  }

  if (authError || !currentUser) {
    return (
      <main className={styles.loadingPage}>
        <p>账号信息加载失败，正在跳转登录页...</p>
        <button onClick={() => router.replace("/login")} type="button">
          返回登录
        </button>
      </main>
    );
  }

  const unreadCount = messages.filter((message) => !message.read).length;

  return (
    <AppShell
      active="waybills"
      isInfoOpen={isInfoOpen}
      messages={messages}
      onInfoClose={() => setIsInfoOpen(false)}
      onInfoOpen={openInfoCenter}
      onLogout={handleLogout}
      unreadCount={unreadCount}
      user={currentUser}
    >
      <section className={styles.workspace}>
        <Link className={styles.backLink} href="/air-waybills">
          <ArrowLeft aria-hidden="true" size={17} />
          返回 Waybills
        </Link>

        {loadState === "loading" && (
          <div className={styles.empty}>正在加载 Waybill 详情...</div>
        )}

        {loadState === "error" && (
          <div className={styles.empty}>暂时无法读取 {number} 的详情</div>
        )}

        {loadState === "ready" && data && (
          <>
            <div className={styles.header}>
              <div>
                <p className={styles.eyebrow}>Waybill Detail</p>
                <h2>{data.summary.number}</h2>
              </div>
              <StatusBadge value={data.summary.status} />
            </div>

            <div className={styles.grid}>
              <section className={styles.panel}>
                <h3>摘要</h3>
                <ValueRow label="Weight(kg)" value={data.summary.weightKgRaw} />
                <ValueRow label="Received" value={data.summary.receivedRaw} />
                <ValueRow label="Parcels" value={data.summary.parcelsRaw} />
                <ValueRow label="In Warehouse" value={data.summary.inWarehouseRaw} />
                <ValueRow label="Released" value={data.summary.releasedRaw} />
                <ValueRow label="Out Bound" value={data.summary.outboundRaw} />
              </section>

              <section className={styles.panel}>
                <h3>原系统详情</h3>
                {data.detail ? (
                  <>
                    <ValueRow label="Waybill Status" value={data.detail.waybillStatus} />
                    <ValueRow label="Uploaded On" value={data.detail.uploadedOnRaw} />
                    <ValueRow label="Date Received" value={data.detail.dateReceivedRaw} />
                    <ValueRow label="Airline" value={data.detail.airlineRaw} />
                    <ValueRow label="Incoming Flight" value={data.detail.incomingFlightRaw} />
                    <ValueRow label="Arrived" value={data.detail.arrivedRaw} />
                    <ValueRow label="Ground Handler" value={data.detail.groundHandlerRaw} />
                    <ValueRow label="Broker" value={data.detail.brokerRaw} />
                    <ValueRow label="Units" value={data.detail.unitsRaw} />
                    <ValueRow label="Units Inbound" value={data.detail.unitsInboundRaw} />
                    <ValueRow label="Units Outbound" value={data.detail.unitsOutboundRaw} />
                    <ValueRow label="Pre-Alert Weight" value={data.detail.preAlertWeightRaw} />
                    <ValueRow label="Gross Weight" value={data.detail.grossWeightRaw} />
                    <ValueRow label="Odd Sized" value={data.detail.oddSizedRaw} />
                  </>
                ) : (
                  <p className={styles.muted}>本单号还没有详情数据。请由管理员执行全量或立即更新。</p>
                )}
              </section>
            </div>

            <section className={styles.panel}>
              <h3>Destinations</h3>
              {data.destinations.length ? (
                <div className={styles.destinations}>
                  {data.destinations.map((destination) => (
                    <article className={styles.destination} key={destination.sortOrder}>
                      <div>
                        <strong>{destination.name}</strong>
                        <span>{destination.country || "-"}</span>
                      </div>
                      <ValueRow label="Units Received" value={destination.unitsReceivedRaw} />
                      <ValueRow label="Units Outbound" value={destination.unitsOutboundRaw} />
                      <ValueRow label="Total Weight" value={destination.totalWeightRaw} />
                      <ValueRow label="Released" value={destination.releasedRaw} />
                    </article>
                  ))}
                </div>
              ) : (
                <p className={styles.muted}>暂无目的地数据。</p>
              )}
            </section>
          </>
        )}
      </section>
    </AppShell>
  );
}

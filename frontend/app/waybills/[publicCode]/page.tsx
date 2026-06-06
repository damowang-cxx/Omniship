"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { AppMessage } from "@/components/InfoCenter";
import {
  getCurrentUser,
  getWaybill,
  isUnauthorizedError,
  logout
} from "@/lib/api";
import type { AppUser, WaybillItem } from "@/lib/types";
import styles from "../page.module.css";

export default function WaybillDetailPage() {
  const params = useParams<{ publicCode: string }>();
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<AppUser | null>(null);
  const [waybill, setWaybill] = useState<WaybillItem | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [messages, setMessages] = useState<AppMessage[]>([]);
  const [isInfoOpen, setIsInfoOpen] = useState(false);

  useEffect(() => {
    async function bootstrap() {
      try {
        const [userResponse, waybillResponse] = await Promise.all([
          getCurrentUser(),
          getWaybill(params.publicCode)
        ]);
        setCurrentUser(userResponse.user);
        setWaybill(waybillResponse);
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
          <p className={styles.eyebrow}>Waybill detail</p>
          <h2>{waybill.number}</h2>
        </section>
      </section>
    </AppShell>
  );
}

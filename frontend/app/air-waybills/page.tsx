"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { AirWaybillsTable } from "@/components/AirWaybillsTable";
import { AirWaybillsToolbar } from "@/components/AirWaybillsToolbar";
import { AppMessage } from "@/components/InfoCenter";
import {
  getAirWaybillScrapeRun,
  getCurrentUser,
  getLatestAirWaybills,
  getScrapeStatus,
  isUnauthorizedError,
  logout,
  triggerAirWaybillFullRefresh,
  triggerAirWaybillRefresh
} from "@/lib/api";
import { filterAirWaybillsByNumber } from "@/lib/search";
import {
  AirWaybillSortState,
  getNextSortState,
  sortAirWaybills,
  SortableAirWaybillKey
} from "@/lib/sort";
import type { AirWaybillItem, AppUser, ScrapeRunSummary } from "@/lib/types";
import styles from "./page.module.css";

type LoadState = "idle" | "loading" | "error";

const ROWS_PER_PAGE_OPTIONS = [25, 50, 100] as const;

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

function runStatusLabel(status?: string | null) {
  const labels: Record<string, string> = {
    running: "运行中",
    success: "成功",
    failed: "失败"
  };

  return status ? labels[status] ?? status : "未抓取";
}

function runModeLabel(mode?: string | null) {
  if (mode === "full") {
    return "全量更新";
  }
  if (mode === "incremental") {
    return "立即更新";
  }
  return mode || "-";
}

function RefreshProgress({ run }: { run: ScrapeRunSummary }) {
  const total = run.totalCount ?? 0;
  const processed = run.processedCount ?? 0;
  const percent = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;

  return (
    <section className={styles.progressPanel} aria-label="任务进度">
      <div className={styles.progressHeader}>
        <div>
          <strong>{runModeLabel(run.mode)}</strong>
          <span>{runStatusLabel(run.status)}</span>
        </div>
        <span>{total > 0 ? `${processed}/${total}` : "准备中"}</span>
      </div>
      <div className={styles.progressTrack}>
        <div className={styles.progressFill} style={{ width: `${percent}%` }} />
      </div>
      <div className={styles.progressStats}>
        <span>新增 {run.insertedCount ?? 0}</span>
        <span>更新 {run.updatedCount ?? 0}</span>
        <span>跳过 {run.skippedCount ?? 0}</span>
        <span>详情失败 {run.detailFailedCount ?? 0}</span>
      </div>
    </section>
  );
}

function WaybillsPager({
  currentPage,
  rowsPerPage,
  totalCount,
  onPageChange,
  onRowsPerPageChange
}: {
  currentPage: number;
  rowsPerPage: number;
  totalCount: number;
  onPageChange: (page: number) => void;
  onRowsPerPageChange: (value: number) => void;
}) {
  if (totalCount === 0) {
    return null;
  }

  const totalPages = Math.max(1, Math.ceil(totalCount / rowsPerPage));
  const start = (currentPage - 1) * rowsPerPage + 1;
  const end = Math.min(totalCount, currentPage * rowsPerPage);

  return (
    <div className={styles.pager} aria-label="Waybills 分页">
      <label>
        <span>每页</span>
        <select
          aria-label="每页显示条数"
          onChange={(event) => onRowsPerPageChange(Number(event.target.value))}
          value={rowsPerPage}
        >
          {ROWS_PER_PAGE_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
      <span className={styles.pageRange}>
        {start}-{end} / {totalCount}
      </span>
      <div className={styles.pageButtons}>
        <button
          aria-label="上一页"
          disabled={currentPage <= 1}
          onClick={() => onPageChange(currentPage - 1)}
          type="button"
        >
          <ChevronLeft aria-hidden="true" size={18} />
        </button>
        <button
          aria-label="下一页"
          disabled={currentPage >= totalPages}
          onClick={() => onPageChange(currentPage + 1)}
          type="button"
        >
          <ChevronRight aria-hidden="true" size={18} />
        </button>
      </div>
    </div>
  );
}

export default function AirWaybillsPage() {
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<AppUser | null>(null);
  const [authState, setAuthState] = useState<"loading" | "ready">("loading");
  const [authError, setAuthError] = useState<string | null>(null);
  const [items, setItems] = useState<AirWaybillItem[]>([]);
  const [latestRun, setLatestRun] = useState<ScrapeRunSummary | null>(null);
  const [status, setStatus] = useState<ScrapeRunSummary | null>(null);
  const [activeRun, setActiveRun] = useState<ScrapeRunSummary | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [query, setQuery] = useState("");
  const [sortState, setSortState] = useState<AirWaybillSortState>(null);
  const [rowsPerPage, setRowsPerPage] = useState<number>(25);
  const [currentPage, setCurrentPage] = useState(1);
  const [messages, setMessages] = useState<AppMessage[]>([]);
  const [isInfoOpen, setIsInfoOpen] = useState(false);

  const addMessage = useCallback(
    (title: string, body: string, tone: AppMessage["tone"] = "error") => {
      setMessages((current) => {
        if (current[0]?.title === title && current[0]?.body === body) {
          return current;
        }

        return [
          {
            id: `${Date.now()}-${current.length}`,
            title,
            body,
            tone,
            createdAt: new Date().toISOString(),
            read: false
          },
          ...current
        ].slice(0, 20);
      });
    },
    []
  );

  const hydrate = useCallback(async (user: AppUser) => {
    setLoadState("loading");
    try {
      const latest = await getLatestAirWaybills();
      const scrapeStatus = user.role === "admin" ? await getScrapeStatus() : null;
      const currentStatus = scrapeStatus?.latestRun ?? latest.latestRun;
      setItems(latest.items);
      setLatestRun(latest.latestRun);
      setStatus(currentStatus);
      setActiveRun(currentStatus?.status === "running" ? currentStatus : null);
      setLoadState("idle");

      if (user.role === "admin" && scrapeStatus?.latestRun?.status === "failed") {
        addMessage(
          "抓取失败",
          scrapeStatus.latestRun.errorMessage || "最近一次抓取未成功"
        );
      }
    } catch (error) {
      if (isUnauthorizedError(error)) {
        router.replace("/login");
        return;
      }
      setLoadState("error");
      if (user.role === "admin") {
        addMessage(
          "后端不可用",
          error instanceof Error ? error.message : "无法连接后端服务"
        );
      }
    }
  }, [addMessage, router]);

  useEffect(() => {
    async function loadCurrentUser() {
      try {
        const response = await getCurrentUser();
        setCurrentUser(response.user);
        setAuthState("ready");
        await hydrate(response.user);
      } catch (error) {
        setAuthError(
          error instanceof Error ? error.message : "无法加载账号信息"
        );
        setAuthState("ready");
        router.replace("/login");
      }
    }

    void loadCurrentUser();
  }, [hydrate, router]);

  useEffect(() => {
    if (!currentUser || currentUser.role !== "admin" || activeRun?.status !== "running") {
      return;
    }

    let cancelled = false;
    const timeout = window.setTimeout(async () => {
      try {
        const run = await getAirWaybillScrapeRun(activeRun.runId);
        if (cancelled) {
          return;
        }
        setActiveRun(run.status === "running" ? run : null);
        setStatus(run);

        if (run.status === "failed") {
          addMessage("抓取失败", run.errorMessage || "抓取任务失败");
          await hydrate(currentUser);
        }
        if (run.status === "success") {
          addMessage("更新完成", `${runModeLabel(run.mode)} 已完成`, "info");
          await hydrate(currentUser);
        }
      } catch (error) {
        if (!cancelled) {
          addMessage(
            "进度读取失败",
            error instanceof Error ? error.message : "无法读取任务进度"
          );
        }
      }
    }, 1800);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [activeRun, addMessage, currentUser, hydrate]);

  const startRefresh = useCallback(async (mode: "full" | "incremental") => {
    if (currentUser?.role !== "admin") {
      return;
    }

    try {
      const result =
        mode === "full"
          ? await triggerAirWaybillFullRefresh()
          : await triggerAirWaybillRefresh();
      setActiveRun(result.status === "running" ? result : null);
      setStatus(result);

      if (result.status === "failed") {
        addMessage("抓取失败", result.errorMessage || "抓取任务失败");
        await hydrate(currentUser);
      }
    } catch (error) {
      const body = error instanceof Error ? error.message : "抓取任务启动失败";
      setStatus((current) =>
        current
          ? {
              ...current,
              status: "failed",
              errorMessage: body
            }
          : null
      );
      addMessage("抓取请求失败", body);
    }
  }, [addMessage, currentUser, hydrate]);

  const handleFullRefresh = useCallback(() => {
    const confirmed = window.confirm(
      "全量更新会翻页读取所有 Waybills 并进入详情页，耗时会明显更长。确认开始？"
    );
    if (confirmed) {
      void startRefresh("full");
    }
  }, [startRefresh]);

  const handleIncrementalRefresh = useCallback(() => {
    void startRefresh("incremental");
  }, [startRefresh]);

  const handleLogout = useCallback(async () => {
    await logout();
    router.replace("/login");
  }, [router]);

  const openInfoCenter = useCallback(() => {
    setIsInfoOpen(true);
    setMessages((current) =>
      current.map((message) => ({ ...message, read: true }))
    );
  }, []);

  const visibleStatus = activeRun ?? status ?? latestRun;
  const filteredItems = useMemo(
    () => filterAirWaybillsByNumber(items, query),
    [items, query]
  );
  const sortedItems = useMemo(
    () => sortAirWaybills(filteredItems, sortState),
    [filteredItems, sortState]
  );
  const totalPages = Math.max(1, Math.ceil(sortedItems.length / rowsPerPage));
  const safeCurrentPage = Math.min(currentPage, totalPages);
  const pagedItems = useMemo(() => {
    const start = (safeCurrentPage - 1) * rowsPerPage;
    return sortedItems.slice(start, start + rowsPerPage);
  }, [rowsPerPage, safeCurrentPage, sortedItems]);

  useEffect(() => {
    setCurrentPage(1);
  }, [query, rowsPerPage, sortState]);

  useEffect(() => {
    setCurrentPage((page) => Math.min(page, totalPages));
  }, [totalPages]);

  const handleSort = useCallback((key: SortableAirWaybillKey) => {
    setSortState((current) => getNextSortState(current, key));
  }, []);
  const isAdmin = currentUser?.role === "admin";
  const unreadCount = messages.filter((message) => !message.read).length;
  const emptyMessage = query
    ? "没有匹配当前 Number 搜索的 Waybill"
    : loadState === "error"
      ? "后端暂时不可用"
      : isAdmin
        ? "暂无最新成功抓取数据"
        : "暂无与你账号绑定的 Waybill";
  const isRefreshing = activeRun?.status === "running";

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
        <div className={styles.workspaceHeader}>
          <div>
            <h2>Waybills</h2>
          </div>
          <div className={styles.meta}>
            <span>最近抓取：{formatDateTime(visibleStatus?.finishedAt)}</span>
            <span>状态：{runStatusLabel(visibleStatus?.status)}</span>
            <span>行数：{items.length}</span>
          </div>
        </div>

        {currentUser.role === "admin" && isRefreshing && activeRun && (
          <RefreshProgress run={activeRun} />
        )}

        <AirWaybillsToolbar
          canUpdate={currentUser.role === "admin"}
          isScraping={isRefreshing}
          onFullRefresh={handleFullRefresh}
          onQueryChange={setQuery}
          onScrape={handleIncrementalRefresh}
          query={query}
        />

        <AirWaybillsTable
          emptyMessage={emptyMessage}
          isLoading={loadState === "loading" && !items.length}
          items={pagedItems}
          onSort={handleSort}
          sortState={sortState}
        />

        <WaybillsPager
          currentPage={safeCurrentPage}
          onPageChange={setCurrentPage}
          onRowsPerPageChange={setRowsPerPage}
          rowsPerPage={rowsPerPage}
          totalCount={sortedItems.length}
        />
      </section>
    </AppShell>
  );
}

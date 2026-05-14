import type { ScrapeRunSummary } from "@/lib/types";
import styles from "./ScrapeStatusCard.module.css";

function formatDate(value?: string | null) {
  if (!value) {
    return "-";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "medium"
  }).format(date);
}

function statusLabel(status?: string | null) {
  if (!status) {
    return "未抓取";
  }

  const labels: Record<string, string> = {
    running: "运行中",
    success: "成功",
    failed: "失败"
  };
  return labels[status] ?? status;
}

export function ScrapeStatusCard({
  latestRun,
  isRefreshing
}: {
  latestRun: ScrapeRunSummary | null;
  isRefreshing?: boolean;
}) {
  const status = isRefreshing ? "running" : latestRun?.status;

  return (
    <section className={styles.grid} aria-label="抓取状态">
      <article className={styles.metric}>
        <span>最近抓取时间</span>
        <strong>{formatDate(latestRun?.finishedAt ?? latestRun?.startedAt)}</strong>
      </article>
      <article className={styles.metric}>
        <span>抓取状态</span>
        <strong data-status={status ?? "idle"}>{statusLabel(status)}</strong>
      </article>
      <article className={styles.metric}>
        <span>抓取行数</span>
        <strong>{latestRun?.rowCount ?? 0}</strong>
      </article>
    </section>
  );
}


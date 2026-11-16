"use client";

import { useCallback, useState } from "react";
import { assignDownstream, getDownstreamDetail, listDownstreamProviders, setDownstreamLocks } from "@/lib/api";
import type { DownstreamBindingSummary, DownstreamDetail } from "@/lib/types";
import styles from "./DownstreamControl.module.css";

function displayTime(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "short", timeStyle: "short", timeZone: "Asia/Shanghai"
  }).format(date);
}

export function DownstreamControl({ publicCode, awb, binding, onChanged }: {
  publicCode: string;
  awb: string;
  binding?: DownstreamBindingSummary;
  onChanged: () => void | Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<DownstreamDetail | null>(null);
  const [providers, setProviders] = useState<{ code: string; name: string }[]>([]);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const show = useCallback(async () => {
    setOpen(true);
    setError(null);
    try {
      const [record, choices] = await Promise.all([
        getDownstreamDetail(publicCode), listDownstreamProviders()
      ]);
      setDetail(record);
      setSelected(record.providerCode ?? "");
      setProviders(choices);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "无法读取下游归属");
    }
  }, [publicCode]);

  const saveAssignment = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const updated = await assignDownstream(publicCode, selected || null);
      setDetail(updated);
      await onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存归属失败");
    } finally {
      setBusy(false);
    }
  }, [onChanged, publicCode, selected]);

  const saveLocks = useCallback(async (payload: { statusLocked?: boolean; milestoneLocks?: string[] }) => {
    setBusy(true);
    setError(null);
    try {
      const updated = await setDownstreamLocks(publicCode, payload);
      setDetail(updated);
      await onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "修改锁定失败");
    } finally {
      setBusy(false);
    }
  }, [onChanged, publicCode]);

  const milestone = detail?.snapshot?.milestones;
  const ajMilestones = milestone && typeof milestone === "object" ? milestone as Record<string, unknown> : null;

  return <>
    <button className={styles.trigger} data-bound={Boolean(binding)} onClick={() => void show()} type="button">
      <span className={styles.dot} />
      {binding?.providerCode ?? "未归属"}
      {binding?.statusLocked ? <small>人工锁定</small> : null}
    </button>
    {open && <div className={styles.backdrop} onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setOpen(false); }}>
      <section aria-label={`${awb} 下游归属`} aria-modal="true" className={styles.dialog} role="dialog">
        <header className={styles.header}>
          <div><span className={styles.eyebrow}>DOWNSTREAM ROUTING</span><h2>提单归属与同步</h2><p>{awb}</p></div>
          <button aria-label="关闭下游归属" className={styles.close} onClick={() => setOpen(false)} type="button">×</button>
        </header>
        <div className={styles.body}>
          <label className={styles.field}>归属系统
            <select disabled={busy || !detail} onChange={(event) => setSelected(event.target.value)} value={selected}>
              <option value="">未归属（人工维护）</option>
              {providers.map((provider) => <option key={provider.code} value={provider.code}>{provider.name}</option>)}
            </select>
          </label>
          <button className={styles.primary} disabled={busy || !detail || selected === (detail.providerCode ?? "")} onClick={() => void saveAssignment()} type="button">保存归属</button>
          {detail?.providerCode && <>
            <div className={styles.divider} />
            <div className={styles.metricGrid}>
              <div><span>下游阶段</span><strong>{detail.remoteStage ?? "等待首次同步"}</strong></div>
              <div><span>完成度</span><strong>{detail.remoteCompletion ?? "—"}</strong></div>
              <div><span>最近查询</span><strong>{displayTime(detail.lastCheckedAt)}</strong></div>
              <div><span>成功同步</span><strong>{displayTime(detail.lastSuccessAt)}</strong></div>
            </div>
            {detail.lastError && <p className={styles.error}>最近错误：{detail.lastError}</p>}
            <div className={styles.locks}>
              <label><input checked={detail.statusLocked} disabled={busy} onChange={(event) => void saveLocks({ statusLocked: event.target.checked })} type="checkbox" />人工锁定提单状态</label>
              <label><input checked={detail.milestoneLocks.includes("customs_clearance_at")} disabled={busy} onChange={(event) => void saveLocks({ milestoneLocks: event.target.checked ? ["customs_clearance_at"] : [] })} type="checkbox" />人工锁定清关时间</label>
            </div>
            <p className={styles.hint}>AJ 清关时间：{displayTime(typeof ajMilestones?.customs_clearance_at === "string" ? ajMilestones.customs_clearance_at : null)}</p>
            {detail.snapshot && <details className={styles.raw}><summary>查看 AJ 原始记录</summary><pre>{JSON.stringify(detail.snapshot, null, 2)}</pre></details>}
          </>}
          {error && <p className={styles.error} role="alert">{error}</p>}
        </div>
      </section>
    </div>}
  </>;
}

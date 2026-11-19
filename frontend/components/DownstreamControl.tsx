"use client";

import { useCallback, useState } from "react";
import { assignDownstream, getDownstreamDetail, listDownstreamProviders, setDownstreamLocks } from "@/lib/api";
import type { DownstreamBindingSummary, DownstreamDetail } from "@/lib/types";
import styles from "./DownstreamControl.module.css";

const MILESTONE_LABELS: Record<string, string> = {
  airline_record_created_at: "航司建档时间", airline_arrived_at: "航司到达时间", aj_warehouse_arrived_at: "AJ 到仓时间",
  noa_at: "NOA 时间", collection_at: "提货时间", scanned_at: "扫描入仓时间",
  customs_clearance_at: "清关时间", outbound_at: "出库完成时间"
};
const DATA_LABELS: Record<string, string> = {
  received_count: "扫描数量", received_total: "应收数量", in_warehouse_count: "入库数量",
  released_count: "放行数量", outbound_count: "出库数量", parcels: "包裹状态", pod_files: "POD 附件"
};
const SYNC_STATE_LABELS: Record<string, string> = {
  synced: "已同步", locked: "人工锁定", unavailable: "暂无来源数据", error: "同步异常"
};

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

  const saveLocks = useCallback(async (payload: { statusLocked?: boolean; milestoneLocks?: string[]; dataLocks?: string[] }) => {
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
              <div><span>最近接口成功</span><strong>{displayTime(detail.lastSuccessAt)}</strong></div>
            </div>
            {detail.lastError && <p className={styles.error}>最近错误：{detail.lastError}</p>}
            <div className={styles.locks}>
              <label><input checked={detail.statusLocked} disabled={busy} onChange={(event) => void saveLocks({ statusLocked: event.target.checked })} type="checkbox" />人工锁定提单状态</label>
            </div>
            <details className={styles.fieldSettings}>
              <summary>各字段人工锁定设置</summary>
              <div className={styles.lockGrid}>
                {Object.entries(MILESTONE_LABELS).map(([field, label]) => <label key={field}>
                  <input type="checkbox" checked={detail.milestoneLocks.includes(field)} disabled={busy} onChange={(event) => {
                    const locks = new Set(detail.milestoneLocks);
                    if (event.target.checked) locks.add(field); else locks.delete(field);
                    void saveLocks({ milestoneLocks: Array.from(locks) });
                  }} />人工锁定{label}
                </label>)}
                {Object.entries(DATA_LABELS).map(([field, label]) => <label key={field}>
                  <input type="checkbox" checked={detail.dataLocks?.includes(field) ?? false} disabled={busy} onChange={(event) => {
                    const locks = new Set(detail.dataLocks ?? []);
                    if (event.target.checked) locks.add(field); else locks.delete(field);
                    void saveLocks({ dataLocks: Array.from(locks) });
                  }} />人工锁定{label}
                </label>)}
              </div>
            </details>
            {detail.syncReport && Object.keys(detail.syncReport).length > 0 && <div className={styles.report}>
              <h3>最近一轮字段同步结果</h3>
              {Object.entries(detail.syncReport).map(([field, result]) => <div className={styles.reportRow} key={field}>
                <strong>{MILESTONE_LABELS[field] || DATA_LABELS[field] || (field === "status" ? "提单状态" : "接口查询")}</strong>
                <span data-state={result.state}>{SYNC_STATE_LABELS[result.state] || result.state}</span>
                {(result.value != null || result.detail) && <p>{result.value != null ? (field in MILESTONE_LABELS ? displayTime(String(result.value)) : String(result.value)) : result.detail}</p>}
                {result.value != null && result.detail && <p>{result.detail}</p>}
              </div>)}
            </div>}
            <p className={styles.hint}>AJ 清关时间：{displayTime(typeof ajMilestones?.customs_clearance_at === "string" ? ajMilestones.customs_clearance_at : null)}</p>
            {detail.snapshot && <details className={styles.raw}><summary>查看 AJ 原始记录</summary><pre>{JSON.stringify(detail.snapshot, null, 2)}</pre></details>}
          </>}
          {error && <p className={styles.error} role="alert">{error}</p>}
        </div>
      </section>
    </div>}
  </>;
}

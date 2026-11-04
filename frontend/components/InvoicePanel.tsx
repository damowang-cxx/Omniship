"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, FilePlus2, History, LoaderCircle, ReceiptText, Stamp, XCircle } from "lucide-react";
import {
  createMyInvoices,
  createUserInvoices,
  downloadMyInvoices,
  downloadUserInvoices,
  getMyInvoiceableDeductions,
  getUserInvoiceableDeductions,
  listMyInvoices,
  listUserInvoices,
  voidUserInvoice
} from "@/lib/api";
import type { InvoiceEligibleDeductionItem, InvoiceItem } from "@/lib/types";
import styles from "./InvoicePanel.module.css";

function money(value: string | number, currency = "EUR") {
  return new Intl.NumberFormat("en-GB", { style: "currency", currency }).format(Number(value));
}

export function InvoicePanel({ userId, admin = false }: { userId?: string; admin?: boolean }) {
  const [tab, setTab] = useState<"eligible" | "history">("history");
  const [eligible, setEligible] = useState<InvoiceEligibleDeductionItem[]>([]);
  const [invoices, setInvoices] = useState<InvoiceItem[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [issuedDate, setIssuedDate] = useState(new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [nextEligible, nextInvoices] = userId
        ? await Promise.all([getUserInvoiceableDeductions(userId), listUserInvoices(userId)])
        : await Promise.all([getMyInvoiceableDeductions(), listMyInvoices()]);
      setEligible(nextEligible);
      setInvoices(nextInvoices);
      setSelected((current) => current.filter((id) => nextEligible.some((item) => item.id === id)));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load invoices");
    } finally {
      setBusy(false);
    }
  }, [userId]);

  useEffect(() => { void load(); }, [load]);

  const totals = useMemo(
    () => eligible.filter((item) => selected.includes(item.id)).reduce((sum, item) => {
      sum[item.currency || "EUR"] += Number(item.totalAmount);
      return sum;
    }, { EUR: 0, GBP: 0 }),
    [eligible, selected]
  );

  const create = async () => {
    if (!selected.length) return;
    setBusy(true);
    setError(null);
    try {
      const result = userId
        ? await createUserInvoices(userId, selected, issuedDate)
        : await createMyInvoices(selected, issuedDate);
      const ids = result.invoices.map((invoice) => invoice.id);
      if (userId) await downloadUserInvoices(userId, ids); else await downloadMyInvoices(ids);
      setSelected([]);
      setTab("history");
      await load();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Unable to create invoice");
    } finally {
      setBusy(false);
    }
  };

  const download = async (invoice: InvoiceItem) => {
    setBusy(true);
    try {
      if (userId) await downloadUserInvoices(userId, [invoice.id]); else await downloadMyInvoices([invoice.id]);
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : "Unable to download invoice");
    } finally { setBusy(false); }
  };

  const voidInvoice = async (invoice: InvoiceItem) => {
    if (!userId) return;
    const reason = window.prompt(`Void ${invoice.invoiceNumber}: enter a reason`);
    if (!reason?.trim()) return;
    setBusy(true);
    try {
      await voidUserInvoice(userId, invoice.id, reason);
      await load();
    } catch (voidError) {
      setError(voidError instanceof Error ? voidError.message : "Unable to void invoice");
    } finally { setBusy(false); }
  };

  return (
    <section className={styles.panel} aria-label="Invoices">
      <header className={styles.header}>
        <div>
          <span className={styles.eyebrow}>EUR / GBP · Customer documents</span>
          <h3>Invoices</h3>
        </div>
        {busy && <LoaderCircle className={styles.loader} aria-label="Loading" size={18} />}
      </header>
      <div className={styles.tabs} role="tablist" aria-label="Invoice sections">
        <button data-active={tab === "eligible"} onClick={() => setTab("eligible")} type="button"><FilePlus2 size={15} />Create invoice</button>
        <button data-active={tab === "history"} onClick={() => setTab("history")} type="button"><History size={15} />Invoice history</button>
      </div>
      {error && <p className={styles.error}>{error}</p>}
      {tab === "eligible" ? (
        <div className={styles.content}>
          <div className={styles.issueBar}>
            <label>Issue date<input type="date" value={issuedDate} onChange={(event) => setIssuedDate(event.target.value)} /></label>
            <div><span>Selected total</span><strong>{totals.GBP ? `${money(totals.EUR)} · ${money(totals.GBP, "GBP")}` : money(totals.EUR)}</strong><small>{selected.length} fee lines · separate invoices per currency</small></div>
            <button disabled={busy || !selected.length} onClick={() => void create()} type="button"><Stamp size={16} />Create & download</button>
          </div>
          {eligible.length ? <div className={styles.tableWrap}><table><thead><tr><th></th><th>Waybill</th><th>Fee type</th><th>Quantity</th><th>Unit rate</th><th>Base charge</th><th>Extra fees</th><th>Invoice total</th></tr></thead><tbody>{eligible.map((item) => <tr key={item.id}><td><input aria-label={`Select ${item.waybillNumber} ${item.feeName}`} checked={selected.includes(item.id)} onChange={(event) => setSelected((current) => event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id))} type="checkbox" /></td><td>{item.waybillNumber}</td><td>{item.feeName}</td><td>{item.quantity}</td><td>{money(item.unitRate, item.currency)}</td><td>{money(item.amount, item.currency)}</td><td>{money(item.extraFeeTotal, item.currency)}</td><td><strong>{money(item.totalAmount, item.currency)}</strong></td></tr>)}</tbody></table></div> : <p className={styles.empty}>No uninvoiced, valid waybill deductions.</p>}
        </div>
      ) : (
        <div className={styles.content}>
          {invoices.length ? <div className={styles.history}>{invoices.map((invoice) => <article className={styles.invoice} data-status={invoice.status} key={invoice.id}><div><span>{invoice.status === "voided" ? "VOIDED" : "ISSUED"}</span><strong>{invoice.invoiceNumber} · {invoice.currency || "EUR"}</strong><small>{invoice.issuedDate} · Due {invoice.dueDate} · {invoice.lines.length} fee lines</small>{invoice.voidReason && <small>Reason: {invoice.voidReason}</small>}</div><b>{money(invoice.totalAmount, invoice.currency)}</b><div className={styles.actions}><button aria-label={`Download ${invoice.invoiceNumber}`} onClick={() => void download(invoice)} type="button"><Download size={15} /></button>{admin && invoice.status === "issued" && <button aria-label={`Void ${invoice.invoiceNumber}`} onClick={() => void voidInvoice(invoice)} type="button"><XCircle size={15} /></button>}</div><details><summary>View details</summary><ul>{invoice.lines.map((line) => <li key={line.id}>{line.waybillNumber} · {line.feeName} · {line.quantity} × {money(line.unitRate, invoice.currency)} · Base {money(line.amount, invoice.currency)} + extra fees {money(line.extraFeeTotal, invoice.currency)} = {money(line.totalAmount, invoice.currency)}</li>)}</ul></details></article>)}</div> : <p className={styles.empty}><ReceiptText size={22} />No invoices have been issued.</p>}
        </div>
      )}
    </section>
  );
}

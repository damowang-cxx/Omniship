"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Save, Stamp } from "lucide-react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { getCurrentUser, getInvoiceSettings, isUnauthorizedError, logout, updateInvoiceSettings } from "@/lib/api";
import type { AppUser, InvoiceSettingsItem } from "@/lib/types";
import styles from "./page.module.css";

const blank: InvoiceSettingsItem = { issuerCompanyName: "", issuerAddressInfo: "", beneficiaryName: "", bankAccount: "", bankNameAndCode: "", branchCode: "", swiftBic: "", bankAddress: "" };

export default function InvoiceSettingsPage() {
  const router = useRouter();
  const [user, setUser] = useState<AppUser | null>(null);
  const [form, setForm] = useState<InvoiceSettingsItem>(blank);
  const [stamp, setStamp] = useState<File | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const account = await getCurrentUser();
      if (account.user.role !== "admin") { router.replace("/waybills"); return; }
      setUser(account.user);
      setForm({ ...blank, ...await getInvoiceSettings() });
    } catch (error) {
      if (isUnauthorizedError(error)) router.replace("/");
      else setNotice(error instanceof Error ? error.message : "Unable to load invoice settings");
    }
  }, [router]);
  useEffect(() => { void load(); }, [load]);
  const change = (key: keyof InvoiceSettingsItem, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const save = async (event: FormEvent) => {
    event.preventDefault(); setSaving(true); setNotice(null);
    try { setForm({ ...blank, ...await updateInvoiceSettings(form, stamp) }); setStamp(null); setNotice("Invoice settings saved."); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Unable to save invoice settings"); }
    finally { setSaving(false); }
  };
  if (!user) return <main className={styles.loading}>Loading invoice settings...</main>;
  return <AppShell active="invoice-settings" isInfoOpen={false} messages={[]} onInfoClose={() => undefined} onInfoOpen={() => undefined} onLogout={async () => { await logout(); router.replace("/"); }} unreadCount={0} user={user}>
    <section className={styles.workspace}><header><div><p>Administrator · invoice source of truth</p><h2>Invoice Settings</h2></div><Stamp size={34} /></header>
      <form onSubmit={save}>
        <section><h3>Issuer</h3><label>Issuer company name<input required value={form.issuerCompanyName ?? ""} onChange={(event) => change("issuerCompanyName", event.target.value)} /></label><label>Issuer address / legal information<textarea required value={form.issuerAddressInfo ?? ""} onChange={(event) => change("issuerAddressInfo", event.target.value)} /></label></section>
        <section><h3>Bank details</h3><div className={styles.grid}><label>Beneficiary Name<input required value={form.beneficiaryName ?? ""} onChange={(event) => change("beneficiaryName", event.target.value)} /></label><label>Bank Account<input required value={form.bankAccount ?? ""} onChange={(event) => change("bankAccount", event.target.value)} /></label><label>Bank name and code<input required value={form.bankNameAndCode ?? ""} onChange={(event) => change("bankNameAndCode", event.target.value)} /></label><label>Branch code<input required value={form.branchCode ?? ""} onChange={(event) => change("branchCode", event.target.value)} /></label><label>Swift/BIC<input required value={form.swiftBic ?? ""} onChange={(event) => change("swiftBic", event.target.value)} /></label><label>Bank Address<textarea required value={form.bankAddress ?? ""} onChange={(event) => change("bankAddress", event.target.value)} /></label></div></section>
        <section><h3>Stamp image</h3><label className={styles.upload}><span>{form.stampOriginalFilename || "No stamp uploaded"}</span><input accept="image/jpeg,image/png,image/webp" onChange={(event) => setStamp(event.target.files?.[0] ?? null)} type="file" /><small>JPG, PNG or WebP · rendered semi-transparent in the waybill detail area</small></label></section>
        {notice && <p className={styles.notice}>{notice}</p>}<button className={styles.save} disabled={saving} type="submit"><Save size={17} />{saving ? "Saving..." : "Save invoice settings"}</button>
      </form>
    </section>
  </AppShell>;
}

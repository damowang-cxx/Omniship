"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Pencil, Save, Stamp, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { getCurrentUser, getInvoiceSettings, getInvoiceStampUrl, isUnauthorizedError, logout, updateInvoiceSettings, updateInvoiceStamp } from "@/lib/api";
import type { AppUser, InvoiceSettingsItem } from "@/lib/types";
import styles from "./page.module.css";

type EditableField = Exclude<keyof InvoiceSettingsItem, "stampOriginalFilename" | "updatedAt">;

const blank: InvoiceSettingsItem = { issuerCompanyName: "", issuerAddressInfo: "", beneficiaryName: "", bankAccount: "", bankNameAndCode: "", branchCode: "", swiftBic: "", bankAddress: "" };
const groups: { title: string; fields: { key: EditableField; label: string; multiline?: boolean }[] }[] = [
  { title: "Issuer", fields: [{ key: "issuerCompanyName", label: "Issuer company name" }, { key: "issuerAddressInfo", label: "Issuer address / legal information", multiline: true }] },
  { title: "Bank details", fields: [{ key: "beneficiaryName", label: "Beneficiary Name" }, { key: "bankAccount", label: "Bank Account" }, { key: "bankNameAndCode", label: "Bank name and code" }, { key: "branchCode", label: "Branch code" }, { key: "swiftBic", label: "Swift/BIC" }, { key: "bankAddress", label: "Bank Address", multiline: true }] }
];

export default function InvoiceSettingsPage() {
  const router = useRouter();
  const [user, setUser] = useState<AppUser | null>(null);
  const [settings, setSettings] = useState<InvoiceSettingsItem>(blank);
  const [editing, setEditing] = useState<EditableField | "stamp" | null>(null);
  const [draft, setDraft] = useState("");
  const [stamp, setStamp] = useState<File | null>(null);
  const [localStampPreview, setLocalStampPreview] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const account = await getCurrentUser();
      if (account.user.role !== "admin") { router.replace("/waybills"); return; }
      setUser(account.user);
      setSettings({ ...blank, ...await getInvoiceSettings() });
    } catch (error) {
      if (isUnauthorizedError(error)) router.replace("/");
      else setNotice(error instanceof Error ? error.message : "Unable to load invoice settings");
    }
  }, [router]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!stamp) { setLocalStampPreview(null); return; }
    const previewUrl = URL.createObjectURL(stamp);
    setLocalStampPreview(previewUrl);
    return () => URL.revokeObjectURL(previewUrl);
  }, [stamp]);

  const beginEdit = (key: EditableField) => { setNotice(null); setDraft(settings[key] || ""); setEditing(key); };
  const saveField = async (key: EditableField) => {
    if (!draft.trim()) { setNotice("This setting cannot be empty."); return; }
    setSaving(true); setNotice(null);
    try { const result = await updateInvoiceSettings({ [key]: draft.trim() }); setSettings((current) => ({ ...current, ...result })); setEditing(null); setNotice("Setting saved."); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Unable to save setting"); }
    finally { setSaving(false); }
  };
  const saveStamp = async () => {
    if (!stamp) { setNotice("Choose a stamp image first."); return; }
    setSaving(true); setNotice(null);
    try { const result = await updateInvoiceStamp(stamp); setSettings((current) => ({ ...current, ...result })); setStamp(null); setEditing(null); setNotice("Stamp image saved."); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Unable to save stamp image"); }
    finally { setSaving(false); }
  };

  if (!user) return <main className={styles.loading}>Loading invoice settings...</main>;
  return <AppShell active="invoice-settings" isInfoOpen={false} messages={[]} onInfoClose={() => undefined} onInfoOpen={() => undefined} onLogout={async () => { await logout(); router.replace("/"); }} unreadCount={0} user={user}>
    <section className={styles.workspace}>
      <header><div><p>Administrator · invoice source of truth</p><h2>Invoice Settings</h2></div><Stamp size={34} /></header>
      <p className={styles.hint}>Each invoice setting is saved independently. Existing invoices keep their original snapshots.</p>
      {groups.map((group) => <section className={styles.group} key={group.title}><h3>{group.title}</h3><div className={styles.fields}>{group.fields.map((field) => {
        const isEditing = editing === field.key;
        return <article className={styles.field} data-editing={isEditing} key={field.key}><div className={styles.fieldHeader}><label>{field.label}</label>{!isEditing && <button onClick={() => beginEdit(field.key)} type="button"><Pencil size={14} />Modify</button>}</div>{isEditing ? <><textarea aria-label={field.label} autoFocus={!field.multiline} className={field.multiline ? styles.textarea : styles.input} onChange={(event) => setDraft(event.target.value)} value={draft} /><div className={styles.editorActions}><button className={styles.cancel} disabled={saving} onClick={() => setEditing(null)} type="button"><X size={14} />Cancel</button><button className={styles.commit} disabled={saving} onClick={() => void saveField(field.key)} type="button"><Save size={14} />{saving ? "Saving..." : "Save"}</button></div></> : <p>{settings[field.key] || "Not configured"}</p>}</article>;
      })}</div></section>)}
      <section className={styles.group}><h3>Stamp image</h3><article className={styles.field} data-editing={editing === "stamp"}><div className={styles.fieldHeader}><label>Invoice seal</label>{editing !== "stamp" && <button onClick={() => { setNotice(null); setEditing("stamp"); }} type="button"><Pencil size={14} />Modify</button>}</div>{editing === "stamp" ? <><div className={styles.stampPreview}>{localStampPreview ? <img alt="New stamp preview" src={localStampPreview} /> : settings.stampOriginalFilename ? <img alt="Current invoice stamp" src={`${getInvoiceStampUrl()}?v=${settings.updatedAt || "current"}`} /> : <span>Select a stamp image to preview it here.</span>}</div><input accept="image/jpeg,image/png,image/webp" onChange={(event) => setStamp(event.target.files?.[0] ?? null)} type="file" /><small>JPG, PNG or WebP · rendered semi-transparent in the detail area</small><div className={styles.editorActions}><button className={styles.cancel} disabled={saving} onClick={() => { setEditing(null); setStamp(null); }} type="button"><X size={14} />Cancel</button><button className={styles.commit} disabled={saving || !stamp} onClick={() => void saveStamp()} type="button"><Check size={14} />{saving ? "Saving..." : "Save stamp"}</button></div></> : <div className={styles.stampPreview}>{settings.stampOriginalFilename ? <img alt="Configured invoice stamp" src={`${getInvoiceStampUrl()}?v=${settings.updatedAt || "current"}`} /> : <span>No stamp uploaded</span>}</div>}</article></section>
      {notice && <p className={styles.notice}>{notice}</p>}
    </section>
  </AppShell>;
}

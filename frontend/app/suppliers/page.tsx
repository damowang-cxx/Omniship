"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDollarSign,
  Factory,
  FileSpreadsheet,
  History,
  Plus,
  Save,
  Settings2,
  X
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import {
  applyRetroactiveBilling,
  createSupplier,
  getBillingSettings,
  getCurrentUser,
  isUnauthorizedError,
  listSuppliers,
  logout,
  publishSupplierVersion,
  updateBillingSettings,
  updateSupplier
} from "@/lib/api";
import type {
  AppUser,
  SupplierFieldRule,
  SupplierItem,
  SupplierSemanticField,
  SupplierVersionConfig,
  RetroactiveBillingResponse
} from "@/lib/types";
import styles from "./page.module.css";

function newRule(index: number): SupplierFieldRule {
  return {
    key: `field_${Date.now()}_${index}`,
    name: "New rule",
    semanticField: null,
    locatorMode: "column",
    locatorValue: "A",
    valueType: "text",
    blankPolicy: "allow",
    caseInsensitive: false,
    allowUnknownCountry: true,
    countryAliases: {},
    constraints: {
      minValue: null,
      maxValue: null,
      minLength: null,
      maxLength: null,
      pattern: null,
      allowedValues: [],
      unique: false
    }
  };
}

function emptyConfig(): SupplierVersionConfig {
  const first = newRule(0);
  first.key = "row_identifier";
  first.name = "Row identifier";
  first.semanticField = "parcel_unit_number";
  return {
    workbook: {
      sheetMode: "first",
      sheetName: null,
      headerRow: 1,
      dataStartRow: 2
    },
    fields: [first],
    billingGroupColumn: "A",
    billingDistinctColumn: "A"
  };
}

function cloneConfig(config: SupplierVersionConfig): SupplierVersionConfig {
  return JSON.parse(JSON.stringify(config)) as SupplierVersionConfig;
}

function legacyBillingColumn(
  config: SupplierVersionConfig,
  fieldKey: string | null | undefined
): string {
  const field = config.fields.find((candidate) => candidate.key === fieldKey);
  return field?.locatorMode === "column" ? field.locatorValue.toUpperCase() : "";
}

function independentDeductionConfig(
  config: SupplierVersionConfig
): SupplierVersionConfig {
  const groupColumn = (
    config.billingGroupColumn ||
    legacyBillingColumn(config, config.billingGroupFieldKey) ||
    legacyBillingColumn(config, config.rowKeyFieldKey)
  ).trim().toUpperCase();
  const distinctColumn = (
    config.billingDistinctColumn ||
    legacyBillingColumn(config, config.billingDistinctFieldKey) ||
    groupColumn
  ).trim().toUpperCase();
  return {
    workbook: config.workbook,
    fields: config.fields,
    billingGroupColumn: groupColumn,
    billingDistinctColumn: distinctColumn
  };
}

function billingColumnLabel(
  config: SupplierVersionConfig,
  kind: "group" | "distinct"
): string {
  const direct = kind === "group"
    ? config.billingGroupColumn
    : config.billingDistinctColumn;
  if (direct) return `Column ${direct}`;
  const legacyKey = kind === "group"
    ? config.billingGroupFieldKey || config.rowKeyFieldKey
    : config.billingDistinctFieldKey;
  const legacyRule = config.fields.find((field) => field.key === legacyKey);
  if (!legacyRule) return "-";
  return legacyRule.locatorMode === "column"
    ? `Column ${legacyRule.locatorValue} (legacy)`
    : `Header ${legacyRule.locatorValue} (legacy)`;
}

function formula(rule: SupplierFieldRule) {
  const parts = [];
  if (rule.blankPolicy === "required") parts.push("required(x)");
  if (rule.blankPolicy === "skip_row") parts.push("blank(x) => skip row");
  parts.push(`${rule.valueType}(x)`);
  if (rule.constraints.minValue !== null && rule.constraints.minValue !== undefined && rule.constraints.minValue !== "") {
    parts.push(`x >= ${rule.constraints.minValue}`);
  }
  if (rule.constraints.maxValue !== null && rule.constraints.maxValue !== undefined && rule.constraints.maxValue !== "") {
    parts.push(`x <= ${rule.constraints.maxValue}`);
  }
  if (rule.constraints.minLength != null) parts.push(`length(x) >= ${rule.constraints.minLength}`);
  if (rule.constraints.maxLength != null) parts.push(`length(x) <= ${rule.constraints.maxLength}`);
  if (rule.constraints.pattern) parts.push(`matches(${rule.constraints.pattern})`);
  if (rule.constraints.allowedValues.length) parts.push(`in(${rule.constraints.allowedValues.join(", ")})`);
  if (rule.constraints.unique) parts.push("unique(x)");
  return parts.join(" AND ");
}

export default function SuppliersPage() {
  const router = useRouter();
  const [user, setUser] = useState<AppUser | null>(null);
  const [suppliers, setSuppliers] = useState<SupplierItem[]>([]);
  const [unitRate, setUnitRate] = useState("3.00");
  const [airportText, setAirportText] = useState("AMS");
  const [taxEffectiveDate, setTaxEffectiveDate] = useState("2026-07-01");
  const [isLoading, setIsLoading] = useState(true);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [editing, setEditing] = useState<SupplierItem | null | "new">(null);
  const [draftName, setDraftName] = useState("");
  const [draftConfig, setDraftConfig] = useState<SupplierVersionConfig>(emptyConfig());
  const [isSaving, setIsSaving] = useState(false);
  const [isRetroactiveOpen, setIsRetroactiveOpen] = useState(false);
  const [retroactiveText, setRetroactiveText] = useState("");
  const [retroactiveResult, setRetroactiveResult] = useState<RetroactiveBillingResponse | null>(null);
  const [isProcessingRetroactive, setIsProcessingRetroactive] = useState(false);

  const load = useCallback(async () => {
    try {
      const [account, supplierResponse, settings] = await Promise.all([
        getCurrentUser(),
        listSuppliers(),
        getBillingSettings()
      ]);
      if (account.user.role !== "admin") {
        router.replace("/waybill-uploads");
        return;
      }
      setUser(account.user);
      setSuppliers(supplierResponse.items);
      setUnitRate(settings.unitTaxEur);
      setAirportText(settings.taxableAirports.join(", "));
      setTaxEffectiveDate(settings.taxEffectiveDate);
    } catch (error) {
      if (isUnauthorizedError(error)) {
        router.replace("/");
        return;
      }
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Unable to load suppliers" });
    } finally {
      setIsLoading(false);
    }
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  const openNew = () => {
    setEditing("new");
    setDraftName("");
    setDraftConfig(emptyConfig());
  };

  const openEdit = (supplier: SupplierItem) => {
    setEditing(supplier);
    setDraftName(supplier.name);
    setDraftConfig(independentDeductionConfig(cloneConfig(supplier.currentVersion.config)));
  };

  const updateRule = (index: number, updater: (rule: SupplierFieldRule) => SupplierFieldRule) => {
    setDraftConfig((current) => ({
      ...current,
      fields: current.fields.map((rule, ruleIndex) => ruleIndex === index ? updater(rule) : rule)
    }));
  };

  const removeRule = (index: number) => {
    setDraftConfig((current) => {
      if (current.fields.length === 1) return current;
      const fields = current.fields.filter((_, ruleIndex) => ruleIndex !== index);
      return { ...current, fields };
    });
  };

  const handleSaveSettings = async (event: FormEvent) => {
    event.preventDefault();
    setNotice(null);
    try {
      const airports = airportText.split(/[,\s]+/).map((value) => value.trim()).filter(Boolean);
      const settings = await updateBillingSettings(unitRate, airports, taxEffectiveDate);
      setUnitRate(settings.unitTaxEur);
      setAirportText(settings.taxableAirports.join(", "));
      setTaxEffectiveDate(settings.taxEffectiveDate);
      setNotice({ tone: "success", text: "Billing settings saved" });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Unable to save billing settings" });
    }
  };

  const handleRetroactiveBilling = async (event: FormEvent) => {
    event.preventDefault();
    const waybillNumbers = retroactiveText.split(/\s+/).map((value) => value.trim()).filter(Boolean);
    if (!waybillNumbers.length) {
      setNotice({ tone: "error", text: "Enter at least one waybill number" });
      return;
    }
    setIsProcessingRetroactive(true);
    setRetroactiveResult(null);
    setNotice(null);
    try {
      const result = await applyRetroactiveBilling(waybillNumbers);
      setRetroactiveResult(result);
      setNotice({
        tone: result.failedCount ? "error" : "success",
        text: `${result.succeededCount} customs deductions recorded; ${result.failedCount} failed`
      });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Unable to process retroactive customs" });
    } finally {
      setIsProcessingRetroactive(false);
    }
  };

  const handleSaveSupplier = async (event: FormEvent) => {
    event.preventDefault();
    if (!editing) return;
    setIsSaving(true);
    setNotice(null);
    const normalizedConfig = independentDeductionConfig(draftConfig);
    setDraftConfig(normalizedConfig);
    try {
      if (editing === "new") {
        await createSupplier(draftName, normalizedConfig);
      } else {
        if (draftName.trim() !== editing.name) {
          await updateSupplier(editing.id, { name: draftName.trim() });
        }
        await publishSupplierVersion(editing.id, normalizedConfig);
      }
      setEditing(null);
      await load();
      setNotice({ tone: "success", text: editing === "new" ? "Supplier created" : "New supplier version published" });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Unable to save supplier" });
    } finally {
      setIsSaving(false);
    }
  };

  const toggleSupplier = async (supplier: SupplierItem) => {
    try {
      await updateSupplier(supplier.id, { status: supplier.status === "active" ? "inactive" : "active" });
      await load();
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Unable to update supplier" });
    }
  };

  const activeCount = useMemo(() => suppliers.filter((supplier) => supplier.status === "active").length, [suppliers]);

  if (isLoading || !user) {
    return <main className={styles.loadingPage}>Loading supplier configuration...</main>;
  }

  return (
    <AppShell active="suppliers" isInfoOpen={false} messages={[]} onInfoClose={() => undefined} onInfoOpen={() => undefined} onLogout={async () => { await logout(); router.replace("/"); }} unreadCount={0} user={user}>
      <section className={styles.workspace}>
        <header className={styles.header}>
          <div><p>Configuration registry</p><h2>Supplier</h2></div>
          <div className={styles.headerActions}>
            <button className={styles.retroactiveButton} onClick={() => { setIsRetroactiveOpen(true); setRetroactiveResult(null); }} type="button"><History aria-hidden="true" size={17} />Tax backfill</button>
            <button onClick={openNew} type="button"><Plus aria-hidden="true" size={17} />Add supplier</button>
          </div>
        </header>

        {notice && <div className={styles.notice} data-tone={notice.tone} role={notice.tone === "error" ? "alert" : "status"}>{notice.text}</div>}

        <form className={styles.settingsCard} onSubmit={handleSaveSettings}>
          <div className={styles.settingsLead}><Settings2 aria-hidden="true" size={22} /><div><span>Global billing policy</span><strong>Tax amount and eligible arrival airports</strong></div></div>
          <label>Unit tax (EUR)<input inputMode="decimal" min="0" onChange={(event) => setUnitRate(event.target.value)} required step="0.01" type="number" value={unitRate} /></label>
          <label>Taxable IATA airports<input onChange={(event) => setAirportText(event.target.value.toUpperCase())} placeholder="AMS, FRA" value={airportText} /></label>
          <label>Tax effective date<input onChange={(event) => setTaxEffectiveDate(event.target.value)} required type="date" value={taxEffectiveDate} /></label>
          <button type="submit"><Save aria-hidden="true" size={16} />Save policy</button>
        </form>

        <section className={styles.registry}>
          <div className={styles.registryHeader}><div><p>Current suppliers</p><h3>Published configurations</h3></div><span>{activeCount} active / {suppliers.length} total</span></div>
          <div className={styles.supplierGrid}>
            {suppliers.map((supplier) => {
              const config = supplier.currentVersion.config;
              return (
                <article className={styles.supplierCard} data-status={supplier.status} key={supplier.id}>
                  <div className={styles.cardTop}><span className={styles.supplierIcon}><Factory aria-hidden="true" size={20} /></span><span className={styles.status}>{supplier.status}</span></div>
                  <div><h4>{supplier.name}</h4><p>Version {supplier.currentVersionNumber} · {config.fields.length} rules</p></div>
                  <dl><div><dt>Worksheet</dt><dd>{config.workbook.sheetMode === "first" ? "First sheet" : config.workbook.sheetName}</dd></div><div><dt>Waybill column</dt><dd>{billingColumnLabel(config, "group")}</dd></div><div><dt>Carton column</dt><dd>{billingColumnLabel(config, "distinct")}</dd></div><div><dt>Data starts</dt><dd>Row {config.workbook.dataStartRow}</dd></div></dl>
                  <footer><button onClick={() => openEdit(supplier)} type="button">Edit & publish</button><button onClick={() => void toggleSupplier(supplier)} type="button">{supplier.status === "active" ? "Deactivate" : "Activate"}</button></footer>
                </article>
              );
            })}
          </div>
        </section>
      </section>

      {editing && (
        <div className={styles.backdrop} role="presentation">
          <form aria-labelledby="supplier-editor-title" aria-modal="true" className={styles.editor} onSubmit={handleSaveSupplier} role="dialog">
            <header className={styles.editorHeader}><div><p>{editing === "new" ? "New configuration" : `Publishing version ${editing.currentVersionNumber + 1}`}</p><h3 id="supplier-editor-title">{editing === "new" ? "Add supplier" : `Edit ${editing.name}`}</h3></div><button aria-label="Close supplier editor" onClick={() => setEditing(null)} type="button"><X aria-hidden="true" size={18} /></button></header>

            <section className={styles.editorSection}><div className={styles.sectionTitle}><span>01</span><div><strong>Supplier information</strong><small>Identity and workbook layout</small></div></div><div className={styles.editorGrid}>
              <label>Supplier name<input onChange={(event) => setDraftName(event.target.value)} required value={draftName} /></label>
              <label>Worksheet<select onChange={(event) => setDraftConfig((current) => ({ ...current, workbook: { ...current.workbook, sheetMode: event.target.value as "first" | "named" } }))} value={draftConfig.workbook.sheetMode}><option value="first">First worksheet</option><option value="named">Named worksheet</option></select></label>
              {draftConfig.workbook.sheetMode === "named" && <label>Worksheet name<input onChange={(event) => setDraftConfig((current) => ({ ...current, workbook: { ...current.workbook, sheetName: event.target.value } }))} required value={draftConfig.workbook.sheetName || ""} /></label>}
              <label>Header row<input min="1" onChange={(event) => setDraftConfig((current) => ({ ...current, workbook: { ...current.workbook, headerRow: Number(event.target.value) } }))} required type="number" value={draftConfig.workbook.headerRow} /></label>
              <label>Data starts at row<input min="2" onChange={(event) => setDraftConfig((current) => ({ ...current, workbook: { ...current.workbook, dataStartRow: Number(event.target.value) } }))} required type="number" value={draftConfig.workbook.dataStartRow} /></label>
            </div></section>

            <section className={styles.editorSection}><div className={styles.sectionTitle}><span>02</span><div><strong>Pre Alert field rules</strong><small>Safe, structured validation — no executable formulas</small></div><button className={styles.addRule} onClick={() => setDraftConfig((current) => ({ ...current, fields: [...current.fields, newRule(current.fields.length)] }))} type="button"><Plus size={15} />Add rule</button></div><div className={styles.rules}>
              {draftConfig.fields.map((rule, index) => (
                <article className={styles.ruleCard} key={rule.key}>
                  <div className={styles.ruleHeader}><strong>Rule {index + 1}</strong><button aria-label={`Remove rule ${index + 1}`} disabled={draftConfig.fields.length === 1} onClick={() => removeRule(index)} type="button"><X size={15} /></button></div>
                  <div className={styles.ruleGrid}>
                    <label>Rule name<input onChange={(event) => updateRule(index, (current) => ({ ...current, name: event.target.value }))} required value={rule.name} /></label>
                    <label>System use<select onChange={(event) => updateRule(index, (current) => ({ ...current, semanticField: (event.target.value || null) as SupplierSemanticField | null }))} value={rule.semanticField || ""}><option value="">Custom validation</option><option value="parcel_unit_number">Parcel Unit Number</option><option value="destination">Destination</option><option value="number_of_items">Number of Items</option><option value="weight_kg">Weight KG</option></select></label>
                    <label>Locate by<select onChange={(event) => updateRule(index, (current) => ({ ...current, locatorMode: event.target.value as "column" | "header" }))} value={rule.locatorMode}><option value="column">Excel column</option><option value="header">Header name</option></select></label>
                    <label>{rule.locatorMode === "column" ? "Column" : "Header"}<input onChange={(event) => updateRule(index, (current) => ({ ...current, locatorValue: rule.locatorMode === "column" ? event.target.value.toUpperCase() : event.target.value }))} required value={rule.locatorValue} /></label>
                    <label>Value type<select onChange={(event) => updateRule(index, (current) => ({ ...current, valueType: event.target.value as SupplierFieldRule["valueType"] }))} value={rule.valueType}><option value="text">Text</option><option value="number">Number</option><option value="integer">Integer</option><option value="country">Country</option></select></label>
                    <label>Blank handling<select onChange={(event) => updateRule(index, (current) => ({ ...current, blankPolicy: event.target.value as SupplierFieldRule["blankPolicy"] }))} value={rule.blankPolicy}><option value="allow">Allow blank</option><option value="required">Warn when blank</option><option value="skip_row">Skip entire row</option></select></label>
                    <label>Minimum<input onChange={(event) => updateRule(index, (current) => ({ ...current, constraints: { ...current.constraints, minValue: event.target.value || null } }))} type="number" value={rule.constraints.minValue || ""} /></label>
                    <label>Maximum<input onChange={(event) => updateRule(index, (current) => ({ ...current, constraints: { ...current.constraints, maxValue: event.target.value || null } }))} type="number" value={rule.constraints.maxValue || ""} /></label>
                    <label>Minimum length<input min="0" onChange={(event) => updateRule(index, (current) => ({ ...current, constraints: { ...current.constraints, minLength: event.target.value ? Number(event.target.value) : null } }))} type="number" value={rule.constraints.minLength ?? ""} /></label>
                    <label>Maximum length<input min="0" onChange={(event) => updateRule(index, (current) => ({ ...current, constraints: { ...current.constraints, maxLength: event.target.value ? Number(event.target.value) : null } }))} type="number" value={rule.constraints.maxLength ?? ""} /></label>
                    <label>Regex pattern<input onChange={(event) => updateRule(index, (current) => ({ ...current, constraints: { ...current.constraints, pattern: event.target.value || null } }))} value={rule.constraints.pattern || ""} /></label>
                    <label>Allowed values<input onChange={(event) => updateRule(index, (current) => ({ ...current, constraints: { ...current.constraints, allowedValues: event.target.value.split(",").map((value) => value.trim()).filter(Boolean) } }))} placeholder="A, B, C" value={rule.constraints.allowedValues.join(", ")} /></label>
                    {rule.valueType === "country" && <label>Country aliases<input onChange={(event) => updateRule(index, (current) => ({ ...current, countryAliases: Object.fromEntries(event.target.value.split(",").map((pair) => pair.split("=").map((value) => value.trim())).filter((pair) => pair.length === 2 && pair[0] && pair[1])) }))} placeholder="Deutschland=DE" value={Object.entries(rule.countryAliases).map(([source, code]) => `${source}=${code}`).join(", ")} /></label>}
                  </div>
                  <div className={styles.ruleOptions}><label><input checked={rule.caseInsensitive} onChange={(event) => updateRule(index, (current) => ({ ...current, caseInsensitive: event.target.checked }))} type="checkbox" />Ignore case</label><label><input checked={rule.constraints.unique} onChange={(event) => updateRule(index, (current) => ({ ...current, constraints: { ...current.constraints, unique: event.target.checked } }))} type="checkbox" />Warn on duplicates</label>{rule.valueType === "country" && <label><input checked={rule.allowUnknownCountry} onChange={(event) => updateRule(index, (current) => ({ ...current, allowUnknownCountry: event.target.checked }))} type="checkbox" />Allow unknown countries</label>}</div>
                  <code>{formula(rule)}</code>
                </article>
              ))}
            </div></section>

            <section className={styles.editorSection}><div className={styles.sectionTitle}><span>03</span><div><strong>Deduction logic</strong><small>Independent Excel columns; not linked to Pre Alert field rules</small></div></div><div className={styles.editorGrid}>
              <label>Waybill number column<input autoCapitalize="characters" maxLength={3} onChange={(event) => setDraftConfig((current) => ({ ...current, billingGroupColumn: event.target.value.toUpperCase() }))} pattern="[A-Za-z]{1,3}" placeholder="C" required value={draftConfig.billingGroupColumn || ""} /></label>
              <label>Carton number column<input autoCapitalize="characters" maxLength={3} onChange={(event) => setDraftConfig((current) => ({ ...current, billingDistinctColumn: event.target.value.toUpperCase() }))} pattern="[A-Za-z]{1,3}" placeholder="X" required value={draftConfig.billingDistinctColumn || ""} /></label>
              <div className={styles.logicSummary}><CheckCircle2 size={18} /><span>Each waybill contributes at least one carton. Repeated rows count the distinct carton values within that waybill only; cartons are never merged across different waybills.</span></div>
            </div></section>

            <footer className={styles.editorFooter}><span><AlertTriangle size={16} />Rule violations become review warnings; workbook structure errors block uploads.</span><div><button onClick={() => setEditing(null)} type="button">Cancel</button><button disabled={isSaving} type="submit"><FileSpreadsheet size={16} />{isSaving ? "Publishing..." : editing === "new" ? "Create supplier" : "Publish new version"}</button></div></footer>
          </form>
        </div>
      )}

      {isRetroactiveOpen && (
        <div className={styles.backdrop} role="presentation">
          <form aria-labelledby="retroactive-title" aria-modal="true" className={`${styles.editor} ${styles.retroactiveEditor}`} onSubmit={handleRetroactiveBilling} role="dialog">
            <header className={styles.editorHeader}>
              <div><p>Legacy customs reconciliation</p><h3 id="retroactive-title">Tax backfill</h3></div>
              <button aria-label="Close tax backfill" onClick={() => setIsRetroactiveOpen(false)} type="button"><X aria-hidden="true" size={18} /></button>
            </header>
            <section className={styles.retroactiveIntro}>
              <span><CircleDollarSign aria-hidden="true" size={24} /></span>
              <div><strong>Process historical waybills one by one</strong><p>Every Pre Alert file is tried against the current active supplier formats. Successful deductions may make the customer balance negative.</p></div>
            </section>
            <section className={styles.retroactiveBody}>
              <label>Waybill numbers
                <textarea aria-label="Waybill numbers" onChange={(event) => setRetroactiveText(event.target.value)} placeholder="784-84063276 020-12345678&#10;Separate numbers with spaces or new lines" required value={retroactiveText} />
              </label>
              <div className={styles.cutoffNote}><History aria-hidden="true" size={17} /><span>Only approved uploads dated on or after <strong>{taxEffectiveDate}</strong> and arriving at {airportText || "a configured airport"} are eligible.</span></div>
            </section>
            {retroactiveResult && (
              <section className={styles.retroactiveResults}>
                <div className={styles.resultSummary}>
                  <div><span>Requested</span><strong>{retroactiveResult.requestedCount}</strong></div>
                  <div data-tone="success"><span>Recorded</span><strong>{retroactiveResult.succeededCount}</strong></div>
                  <div data-tone="error"><span>Failed</span><strong>{retroactiveResult.failedCount}</strong></div>
                </div>
                {retroactiveResult.succeeded.length > 0 && <div className={styles.resultGroup}><h4>Recorded deductions</h4>{retroactiveResult.succeeded.map((item) => <div className={styles.resultRow} key={item.waybillNumber}><div><strong>{item.waybillNumber}</strong><span>{item.supplierName} v{item.supplierVersionNumber}</span></div><span>{item.billableUnitCount} cartons × €{item.unitRate}</span><strong>€{item.amount}</strong></div>)}</div>}
                {retroactiveResult.failed.length > 0 && <div className={`${styles.resultGroup} ${styles.failureGroup}`}><h4>Failed waybills</h4>{retroactiveResult.failed.map((item) => <div className={styles.failureRow} key={item.waybillNumber}><strong>{item.waybillNumber}</strong><span>{item.reason}</span></div>)}</div>}
              </section>
            )}
            <footer className={styles.editorFooter}><span><AlertTriangle size={16} />Already billed waybills are rejected to prevent duplicate deductions.</span><div><button onClick={() => setIsRetroactiveOpen(false)} type="button">Close</button><button disabled={isProcessingRetroactive} type="submit"><CircleDollarSign size={16} />{isProcessingRetroactive ? "Processing..." : "Process backfill"}</button></div></footer>
          </form>
        </div>
      )}
    </AppShell>
  );
}
